"""Custom admin dashboard.

Server-rendered with Django templates + Tailwind (CDN) + Alpine.js for the
interactive bits. Uses Django's session auth (NOT the WordPress cookie auth
the mobile app uses).

Only users with is_dashboard_admin=True can access. The bootstrap admin
created by `manage.py create_admin` has this flag set automatically.
"""
import logging

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.utils.text import slugify
from django.utils import timezone
from django.views import View
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView,
)

from apps.content.models import (
    Article, ContentCategory, ArticleView, Ebook, EbookDownload,
)
from apps.videos.models import Video, VideoCollection, VideoComment, VideoView
from apps.videos import bunny
from apps.rewards.models import RewardLedger, Badge
from apps.quiz.models import Submission

User = get_user_model()
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- 
# Auth gate
# ---------------------------------------------------------------------------

class DashboardAdminRequired(UserPassesTestMixin):
    login_url = reverse_lazy('dashboard:login')

    def test_func(self):
        u = self.request.user
        return bool(u.is_authenticated and getattr(u, 'is_dashboard_admin', False))

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            messages.error(self.request, "You don't have access to the dashboard.")
            return redirect('dashboard:login')
        return super().handle_no_permission()


class DashboardView(DashboardAdminRequired, LoginRequiredMixin):
    """Convenience: combines login + dashboard-admin gate."""
    pass


# --------------------------------------------------------------------------- 
# Login / logout
# ---------------------------------------------------------------------------

class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'w-full px-4 py-3 rounded-lg border border-stone-300 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition outline-none',
        'placeholder': 'you@alluora.com',
        'autocomplete': 'email',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'w-full px-4 py-3 rounded-lg border border-stone-300 focus:border-orange-500 focus:ring-2 focus:ring-orange-200 transition outline-none',
        'placeholder': '••••••••',
        'autocomplete': 'current-password',
    }))


class LoginView(View):
    template = 'dashboard/login.html'

    def get(self, request):
        if request.user.is_authenticated and getattr(request.user, 'is_dashboard_admin', False):
            return redirect('dashboard:home')
        return render(request, self.template, {'form': LoginForm()})

    def post(self, request):
        form = LoginForm(request.POST)
        if not form.is_valid():
            return render(request, self.template, {'form': form})

        email = form.cleaned_data['email']
        password = form.cleaned_data['password']

        # We use email as the login identifier; resolve to username for authenticate().
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = None

        authed = authenticate(request, username=user.username, password=password) if user else None

        if not authed or not getattr(authed, 'is_dashboard_admin', False):
            messages.error(request, 'Invalid credentials or no dashboard access.')
            return render(request, self.template, {'form': form})

        login(request, authed)
        return redirect('dashboard:home')


class LogoutView(View):
    def post(self, request):
        logout(request)
        return redirect('dashboard:login')

    def get(self, request):
        # Allow GET for convenience but it's POST-preferred.
        return self.post(request)


# --------------------------------------------------------------------------- 
# Home / overview
# ---------------------------------------------------------------------------

class HomeView(DashboardView, TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update({
            'article_count': Article.objects.count(),
            'published_articles': Article.objects.filter(status=Article.STATUS_PUBLISHED).count(),
            'video_count': Video.objects.count(),
            'video_ready_count': Video.objects.filter(status=Video.STATUS_READY).count(),
            'user_count': User.objects.filter(is_dashboard_admin=False).count(),
            'recent_submissions': Submission.objects.select_related(
                'user', 'quiz', 'primary_result',
            )[:8],
            'points_issued': RewardLedger.objects.filter(points__gt=0).aggregate(
                total=Sum('points'),
            )['total'] or 0,
            'bunny_configured': bunny.is_configured(),
        })
        return ctx


# --------------------------------------------------------------------------- 
# Articles
# ---------------------------------------------------------------------------

class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ('title', 'summary', 'body', 'category', 'cover_image',
                  'cover_image_url', 'status', 'published_at', 'is_featured')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'summary': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'body': forms.Textarea(attrs={'class': 'form-input font-mono', 'rows': 16}),
            'cover_image_url': forms.URLInput(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'published_at': forms.DateTimeInput(
                attrs={'class': 'form-input', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['published_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
        ]
        self.fields['published_at'].required = False


class ArticleListView(DashboardView, ListView):
    model = Article
    template_name = 'dashboard/articles.html'
    paginate_by = 20
    context_object_name = 'articles'

    def get_queryset(self):
        qs = Article.objects.select_related('category', 'author').order_by('-updated_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(summary__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class ArticleCreateView(DashboardView, CreateView):
    model = Article
    form_class = ArticleForm
    template_name = 'dashboard/article_form.html'
    success_url = reverse_lazy('dashboard:articles')

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, 'Article created.')
        return super().form_valid(form)


class ArticleEditView(DashboardView, UpdateView):
    model = Article
    form_class = ArticleForm
    template_name = 'dashboard/article_form.html'
    success_url = reverse_lazy('dashboard:articles')

    def form_valid(self, form):
        messages.success(self.request, 'Article saved.')
        return super().form_valid(form)


class ArticleDeleteView(DashboardView, DeleteView):
    model = Article
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:articles')

    def form_valid(self, form):
        messages.success(self.request, 'Article deleted.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Ebooks (Library) — downloadable PDFs, optional members-only gate
# ---------------------------------------------------------------------------

class EbookForm(forms.ModelForm):
    class Meta:
        model = Ebook
        fields = (
            'title', 'description', 'author_name', 'category',
            'cover_image', 'cover_image_url', 'pdf_file',
            'page_count', 'is_members_only',
            'status', 'published_at',
        )
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'author_name': forms.TextInput(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'cover_image_url': forms.URLInput(attrs={'class': 'form-input'}),
            'page_count': forms.NumberInput(attrs={'class': 'form-input', 'min': 0}),
            'status': forms.Select(attrs={'class': 'form-input'}),
            'published_at': forms.DateTimeInput(
                attrs={'class': 'form-input', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['published_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
        ]
        self.fields['published_at'].required = False
        # PDF is required when creating; on edit it stays optional so
        # the admin can update the metadata without re-uploading.
        if self.instance and self.instance.pk:
            self.fields['pdf_file'].required = False

    def clean_pdf_file(self):
        f = self.cleaned_data.get('pdf_file')
        if not f:
            return f
        # Best-effort MIME check (browsers don't always send it for PDFs,
        # so we accept anything that ends .pdf as a fallback).
        name_ok = f.name.lower().endswith('.pdf')
        ct = (getattr(f, 'content_type', '') or '').lower()
        type_ok = ct in ('', 'application/pdf', 'application/octet-stream')
        if not (name_ok and type_ok):
            raise forms.ValidationError('Only PDF files are supported.')
        # Cap at 50 MB — Railway's request body limit + storage cost.
        max_bytes = 50 * 1024 * 1024
        if getattr(f, 'size', 0) > max_bytes:
            raise forms.ValidationError(
                f'PDF is {f.size // (1024 * 1024)} MB. Max is 50 MB.'
            )
        return f


class EbookListView(DashboardView, ListView):
    model = Ebook
    template_name = 'dashboard/ebooks.html'
    paginate_by = 20
    context_object_name = 'ebooks'

    def get_queryset(self):
        qs = Ebook.objects.select_related('category').order_by('-updated_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(author_name__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')

        # Top-line download stats — all-time, 7-day, 30-day windows.
        # Counts ALL download events (free + members-only, signed-in +
        # guest), so the number matches what the admin sees in the
        # per-ebook history. Empty library returns zeros, not None.
        now = timezone.now()
        d7 = now - timezone.timedelta(days=7)
        d30 = now - timezone.timedelta(days=30)
        downloads = EbookDownload.objects.all()
        ctx['stats'] = {
            'ebook_count': Ebook.objects.count(),
            'published_count': Ebook.objects.filter(
                status=Ebook.STATUS_PUBLISHED).count(),
            'members_only_count': Ebook.objects.filter(
                is_members_only=True).count(),
            'downloads_all': downloads.count(),
            'downloads_d7': downloads.filter(created_at__gte=d7).count(),
            'downloads_d30': downloads.filter(created_at__gte=d30).count(),
        }
        # Top 5 ebooks by downloads in the last 30 days — drives the
        # "what's working" admin instinct without making them sort the
        # whole table.
        ctx['top_ebooks'] = list(
            Ebook.objects.annotate(
                window_downloads=Count(
                    'download_events',
                    filter=Q(download_events__created_at__gte=d30),
                ),
            ).filter(window_downloads__gt=0)
             .order_by('-window_downloads')[:5]
        )
        return ctx


class EbookCreateView(DashboardView, CreateView):
    model = Ebook
    form_class = EbookForm
    template_name = 'dashboard/ebook_form.html'
    success_url = reverse_lazy('dashboard:ebooks')

    def form_valid(self, form):
        messages.success(self.request, 'Ebook uploaded.')
        return super().form_valid(form)


class EbookEditView(DashboardView, UpdateView):
    model = Ebook
    form_class = EbookForm
    template_name = 'dashboard/ebook_form.html'
    success_url = reverse_lazy('dashboard:ebooks')

    def form_valid(self, form):
        messages.success(self.request, 'Ebook saved.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Recent download events for this ebook — drives the activity
        # panel below the edit form. Capped to 25 rows so a popular
        # ebook doesn't make the edit page do an unbounded query.
        ctx['recent_downloads'] = (
            self.object.download_events
            .select_related('user')
            .order_by('-created_at')[:25]
        )
        # Quick unique-user count for the panel header. Distinct on
        # user_id excludes the NULLs (guests), which is what we want
        # — "X members have downloaded this".
        ctx['unique_downloaders'] = (
            self.object.download_events
            .filter(user__isnull=False)
            .values('user_id').distinct().count()
        )
        ctx['guest_downloads'] = (
            self.object.download_events.filter(user__isnull=True).count()
        )
        return ctx


class AdminCreateForm(forms.Form):
    """Used by AdminCreateView. Not a ModelForm because we need
    password handling + uniqueness checks tailored to the dashboard's
    expectations (email is the login identifier, not a username)."""
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'autocomplete': 'off',
        }),
    )
    first_name = forms.CharField(
        max_length=80, required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )
    last_name = forms.CharField(
        max_length=80, required=False,
        widget=forms.TextInput(attrs={'class': 'form-input'}),
    )
    password = forms.CharField(
        min_length=8,
        widget=forms.PasswordInput(attrs={
            'class': 'form-input',
            'autocomplete': 'new-password',
        }),
        help_text='Min 8 characters. Share securely with the new admin '
                  'and have them change it after first login.',
    )

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            if existing.is_dashboard_admin:
                raise forms.ValidationError(
                    'That email already has dashboard access.'
                )
            # Existing app user — we don't want to silently promote a
            # mobile-app customer to dashboard admin via this form, so
            # block it. Operator can do that explicitly via the User
            # detail page or via /django-admin/.
            raise forms.ValidationError(
                'An app user already exists with that email. Promote '
                'them via the user detail page instead.'
            )
        return email


class AdminListView(DashboardView, ListView):
    """List of all dashboard admins. The main admin is filtered out
    for viewers who AREN'T the main admin themselves (the requirement:
    "main admin account is hidden from other admin accounts")."""
    template_name = 'dashboard/admins.html'
    paginate_by = 30
    context_object_name = 'admins'

    def get_queryset(self):
        qs = User.objects.filter(is_dashboard_admin=True).order_by(
            '-is_main_admin', 'date_joined',
        )
        if not self.request.user.is_main_admin:
            qs = qs.filter(is_main_admin=False)
        return qs


class AdminCreateView(DashboardView, View):
    """Add a new dashboard admin. Any existing admin can do this;
    the new admin is created with is_dashboard_admin=True but never
    is_main_admin=True (the main flag can only come from the bootstrap
    command). Idempotent on email collision via the form's clean
    method."""
    template = 'dashboard/admin_form.html'

    def get(self, request):
        return render(request, self.template, {'form': AdminCreateForm()})

    def post(self, request):
        form = AdminCreateForm(request.POST)
        if not form.is_valid():
            return render(request, self.template, {'form': form})

        email = form.cleaned_data['email']
        # Build a unique username from the email local-part; same
        # collision-avoidance pattern as the WP plugin's registration.
        base_username = email.split('@')[0][:140] or 'admin'
        username = base_username
        i = 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}{i}'
            i += 1

        new_admin = User(
            email=email,
            username=username,
            first_name=form.cleaned_data.get('first_name', ''),
            last_name=form.cleaned_data.get('last_name', ''),
            is_staff=True,
            is_dashboard_admin=True,
            is_main_admin=False,
        )
        new_admin.set_password(form.cleaned_data['password'])
        new_admin.save()
        messages.success(
            request,
            f'Added dashboard admin: {email}. They can sign in now.',
        )
        return redirect('dashboard:admins')


class AdminRevokeView(DashboardView, View):
    """POST /dashboard/admins/<pk>/revoke/ — drops is_dashboard_admin
    on the target user. The user account itself stays (so any owned
    content / authored articles keep their author reference); only
    dashboard access is removed.

    Protections:
      - The main admin can NEVER be revoked through this endpoint.
      - A user cannot revoke themselves (would lock out the dashboard
        if they're the last admin standing — and is just confusing UX).
    """

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk, is_dashboard_admin=True)
        if target.is_main_admin:
            messages.error(request, 'The main admin cannot be revoked.')
            return redirect('dashboard:admins')
        if target.pk == request.user.pk:
            messages.error(
                request,
                "You can't revoke your own dashboard access. "
                'Ask another admin to do it.',
            )
            return redirect('dashboard:admins')
        target.is_dashboard_admin = False
        target.is_staff = False
        target.save(update_fields=['is_dashboard_admin', 'is_staff'])
        messages.success(
            request,
            f'Removed dashboard access for {target.display_name_or_email}.',
        )
        return redirect('dashboard:admins')


class EbookDeleteView(DashboardView, DeleteView):
    model = Ebook
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:ebooks')

    def form_valid(self, form):
        # Best-effort delete of the underlying PDF + cover from storage.
        # FileField doesn't auto-delete its file on row delete.
        try:
            if self.object.pdf_file:
                self.object.pdf_file.delete(save=False)
        except Exception:
            logger.exception('Ebook PDF cleanup failed')
        try:
            if self.object.cover_image:
                self.object.cover_image.delete(save=False)
        except Exception:
            logger.exception('Ebook cover cleanup failed')
        messages.success(self.request, 'Ebook deleted.')
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Content categories — taxonomy for articles
# ---------------------------------------------------------------------------

class ContentCategoryForm(forms.ModelForm):
    class Meta:
        model = ContentCategory
        fields = ('name', 'slug', 'sort_order')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'slug': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'leave blank to auto-generate from the name',
            }),
            'sort_order': forms.NumberInput(attrs={'class': 'form-input'}),
        }


class CategoryListView(DashboardView, ListView):
    model = ContentCategory
    template_name = 'dashboard/categories.html'
    paginate_by = 50
    context_object_name = 'categories'

    def get_queryset(self):
        # Annotate the article count so the template can render it without
        # needing a custom template filter to look up a dict by id.
        return ContentCategory.objects.annotate(article_count=Count('articles'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = ContentCategoryForm()
        return ctx


class CategoryCreateView(DashboardView, CreateView):
    model = ContentCategory
    form_class = ContentCategoryForm
    template_name = 'dashboard/categories.html'
    success_url = reverse_lazy('dashboard:categories')

    def form_valid(self, form):
        messages.success(self.request, f'Category "{form.instance.name}" added.')
        return super().form_valid(form)

    def form_invalid(self, form):
        # Reuse the list page's render so the error appears inline.
        view = CategoryListView()
        view.setup(self.request)
        view.object_list = view.get_queryset()
        ctx = view.get_context_data()
        ctx['form'] = form
        return self.render_to_response(ctx)


class CategoryEditView(DashboardView, UpdateView):
    model = ContentCategory
    form_class = ContentCategoryForm
    template_name = 'dashboard/category_form.html'
    success_url = reverse_lazy('dashboard:categories')

    def form_valid(self, form):
        messages.success(self.request, 'Category saved.')
        return super().form_valid(form)


class CategoryDeleteView(DashboardView, DeleteView):
    model = ContentCategory
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:categories')

    def form_valid(self, form):
        messages.success(self.request, 'Category deleted.')
        return super().form_valid(form)


class CategoryApiCreateView(DashboardView, View):
    """JSON endpoint used by the article-edit page's inline "+ New category"
    widget. Accepts POST {name}, returns {id, name, slug} so the JS can
    append the new option to the dropdown without a full page reload."""

    def post(self, request):
        name = (request.POST.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)
        if len(name) > 80:
            return JsonResponse({'error': 'Name too long (max 80).'}, status=400)
        # Pick a unique slug; if the name collides with an existing category
        # just return that one (idempotent).
        existing = ContentCategory.objects.filter(name__iexact=name).first()
        if existing:
            return JsonResponse({
                'id': existing.id,
                'name': existing.name,
                'slug': existing.slug,
                'existing': True,
            })
        slug = slugify(name)[:100]
        base = slug
        counter = 1
        while ContentCategory.objects.filter(slug=slug).exists():
            slug = f'{base}-{counter}'[:100]
            counter += 1
        cat = ContentCategory.objects.create(name=name, slug=slug)
        return JsonResponse({
            'id': cat.id,
            'name': cat.name,
            'slug': cat.slug,
            'existing': False,
        }, status=201)


# ---------------------------------------------------------------------------
# Video collections — taxonomy for videos
# ---------------------------------------------------------------------------

class VideoCollectionForm(forms.ModelForm):
    class Meta:
        model = VideoCollection
        fields = ('name', 'slug', 'sort_order')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input'}),
            'slug': forms.TextInput(attrs={'class': 'form-input'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-input'}),
        }


class CollectionListView(DashboardView, ListView):
    model = VideoCollection
    template_name = 'dashboard/collections.html'
    paginate_by = 50
    context_object_name = 'collections'

    def get_queryset(self):
        return VideoCollection.objects.annotate(video_count=Count('videos'))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form'] = VideoCollectionForm()
        return ctx


class CollectionCreateView(DashboardView, CreateView):
    model = VideoCollection
    form_class = VideoCollectionForm
    template_name = 'dashboard/collections.html'
    success_url = reverse_lazy('dashboard:collections')

    def form_valid(self, form):
        messages.success(self.request, f'Collection "{form.instance.name}" added.')
        return super().form_valid(form)

    def form_invalid(self, form):
        view = CollectionListView()
        view.setup(self.request)
        view.object_list = view.get_queryset()
        ctx = view.get_context_data()
        ctx['form'] = form
        return self.render_to_response(ctx)


class CollectionEditView(DashboardView, UpdateView):
    model = VideoCollection
    form_class = VideoCollectionForm
    template_name = 'dashboard/collection_form.html'
    success_url = reverse_lazy('dashboard:collections')

    def form_valid(self, form):
        messages.success(self.request, 'Collection saved.')
        return super().form_valid(form)


class CollectionDeleteView(DashboardView, DeleteView):
    model = VideoCollection
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:collections')

    def form_valid(self, form):
        messages.success(self.request, 'Collection deleted.')
        return super().form_valid(form)


# --------------------------------------------------------------------------- 
# Videos
# ---------------------------------------------------------------------------

class VideoMetaForm(forms.ModelForm):
    """Used after upload to edit metadata. Upload itself happens via the
    /api/v1/videos/admin/* endpoints with TUS to Bunny directly."""
    class Meta:
        model = Video
        fields = ('title', 'description', 'collection',
                  'min_tier', 'publish_at',
                  'is_featured', 'is_published', 'comments_enabled')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'collection': forms.Select(attrs={'class': 'form-input'}),
            'min_tier': forms.Select(attrs={'class': 'form-select'}),
            'publish_at': forms.DateTimeInput(
                attrs={'class': 'form-input', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }
        # The widget format above only renders correctly if the field's
        # input_formats list also accepts the HTML5 datetime-local format.
        # Django 4+ sets reasonable defaults but we override to be safe.

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['publish_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
        ]


class ReelMetaForm(forms.ModelForm):
    """Reel form: same as VideoMetaForm minus the collection field."""
    class Meta:
        model = Video
        fields = ('title', 'description',
                  'min_tier', 'publish_at',
                  'is_featured', 'is_published', 'comments_enabled')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'min_tier': forms.Select(attrs={'class': 'form-select'}),
            'publish_at': forms.DateTimeInput(
                attrs={'class': 'form-input', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M',
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['publish_at'].input_formats = [
            '%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S',
        ]


class VideoListView(DashboardView, ListView):
    """Long-form videos (is_reel=False). Reels live on a separate page."""
    model = Video
    template_name = 'dashboard/videos.html'
    paginate_by = 20
    context_object_name = 'videos'
    is_reel = False  # subclassed to True for the Reel admin section

    def get_queryset(self):
        # Sync first so status / dimensions on this page reflect the
        # latest Bunny snapshot. Cap to the first page worth of rows
        # so the request doesn't fan out hundreds of API calls.
        page_qs = Video.objects.filter(is_reel=self.is_reel) \
            .select_related('collection') \
            .order_by('-created_at')[:self.paginate_by]
        _sync_videos_for_list(list(page_qs))
        # `view_count` is the authoritative play count, computed from
        # VideoView (the /track endpoint appends one row per session).
        # Video.views is no longer used by the dashboard — it was a
        # legacy mirror of Bunny's number which doesn't see direct
        # HLS plays.
        return Video.objects.filter(is_reel=self.is_reel) \
            .select_related('collection') \
            .annotate(
                comment_count=Count('comments', distinct=True),
                view_count=Count('view_events', distinct=True),
            ) \
            .order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['bunny_configured'] = bunny.is_configured()
        ctx['collections'] = VideoCollection.objects.all()
        ctx['is_reel_section'] = self.is_reel
        return ctx


class ReelListView(VideoListView):
    """Short-form clips (is_reel=True), 20-90s, no collection."""
    template_name = 'dashboard/reels.html'
    is_reel = True


class VideoCreateView(DashboardView, TemplateView):
    """Renders the upload page. Actual upload uses the JSON API + tus-js-client."""
    template_name = 'dashboard/video_create.html'
    is_reel = False  # subclassed to True for reels

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['bunny_configured'] = bunny.is_configured()
        ctx['collections'] = VideoCollection.objects.all()
        ctx['min_tier_choices'] = Video.MIN_TIER_CHOICES
        ctx['is_reel_section'] = self.is_reel
        return ctx


class ReelCreateView(VideoCreateView):
    """Reel upload — same flow as videos but no collection picker, and
    a 20-90s duration hint."""
    template_name = 'dashboard/reel_create.html'
    is_reel = True


# Bunny's numeric status → our string. Kept module-level so both the
# detail and list views can use it.
_BUNNY_STATUS_MAP = {
    0: Video.STATUS_CREATED,
    1: Video.STATUS_UPLOADING,
    2: Video.STATUS_PROCESSING,
    3: Video.STATUS_PROCESSING,
    4: Video.STATUS_READY,
    5: Video.STATUS_FAILED,
    6: Video.STATUS_FAILED,
}


def _sync_bunny_for_video(video) -> bool:
    """Pull current status + dims from Bunny for one video and persist
    any changes. Returns True iff the row was updated. Best-effort —
    swallows BunnyStreamError so a flaky API call doesn't break the
    page render."""
    if not video.bunny_video_guid or not bunny.is_configured():
        return False
    try:
        bunny_data = bunny.get_video(video.bunny_video_guid)
    except bunny.BunnyStreamError as exc:
        logger.warning('Bunny sync failed for video %s: %s', video.pk, exc)
        return False
    bunny_status = bunny_data.get('status', 0)
    new_status = _BUNNY_STATUS_MAP.get(bunny_status, video.status)
    update_fields = []
    if new_status != video.status:
        video.status = new_status
        update_fields.append('status')
    if bunny_data.get('length'):
        video.duration_seconds = int(bunny_data['length'])
        update_fields.append('duration_seconds')
    if bunny_data.get('width'):
        video.width = bunny_data['width']
        update_fields.append('width')
    if bunny_data.get('height'):
        video.height = bunny_data['height']
        update_fields.append('height')
    # Bunny's `views` counter is intentionally NOT mirrored here.
    # We track plays ourselves via VideoView (incremented by the
    # /track endpoint), and Bunny's number doesn't see direct HLS
    # plays from the app — overwriting Video.views with it would
    # constantly reset the dashboard count to 0. The list pages
    # render `view_count` annotated from VideoView instead.
    if update_fields:
        video.save(update_fields=update_fields)
        return True
    return False


def _sync_videos_for_list(videos):
    """Auto-sync a batch of videos before rendering the list.

    Status sync runs only for non-terminal rows (cheap and avoids stale
    'Processing' badges). View counts re-sync for ALL videos so the
    Views column reflects what Bunny is showing in their dashboard,
    capped to the visible page so the load stays bounded.
    """
    if not bunny.is_configured():
        return
    targets = [v for v in videos if v.bunny_video_guid][:30]
    if not targets:
        return
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(_sync_bunny_for_video, targets))


class VideoEditView(DashboardView, UpdateView):
    model = Video
    form_class = VideoMetaForm
    template_name = 'dashboard/video_edit.html'
    success_url = reverse_lazy('dashboard:videos')
    is_reel = False  # subclassed to True for ReelEditView

    def get_queryset(self):
        # Lock each section to its own kind so /dashboard/videos/<id>/
        # can't accidentally edit a reel and vice versa.
        return super().get_queryset().filter(is_reel=self.is_reel)

    def get_object(self, queryset=None):
        # Sync from Bunny on every load while the video isn't already
        # Ready/Failed, so the form reflects the live state.
        obj = super().get_object(queryset=queryset)
        if obj.status not in (Video.STATUS_READY, Video.STATUS_FAILED):
            _sync_bunny_for_video(obj)
        return obj

    def form_valid(self, form):
        messages.success(
            self.request,
            'Reel updated.' if self.is_reel else 'Video updated.',
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # The Bunny iframe player URL is /embed/<library_id>/<guid> —
        # without the library id it just renders a black box. Expose
        # the configured library id so the template can build the URL.
        from django.conf import settings as dj_settings
        ctx['bunny_library_id'] = dj_settings.BUNNY_STREAM_LIBRARY_ID
        # 50 most recent comments for the moderation panel.
        ctx['comments'] = (
            self.object.comments
            .select_related('user')
            .order_by('-created_at')[:50]
        )
        ctx['comment_count'] = self.object.comments.count()
        ctx['like_count'] = self.object.likes.count()
        # Authoritative play count from VideoView — replaces the old
        # Bunny-mirrored Video.views that was reading 0.
        ctx['view_count'] = self.object.view_events.count()
        ctx['is_reel_section'] = self.is_reel
        # Reels are expected to be 20-90s; surface a warning to the
        # admin if the actual duration falls outside that range.
        if self.is_reel and self.object.duration_seconds:
            ctx['reel_duration_warning'] = (
                self.object.duration_seconds < 20
                or self.object.duration_seconds > 90
            )
        return ctx


class ReelEditView(VideoEditView):
    form_class = ReelMetaForm
    template_name = 'dashboard/reel_edit.html'
    success_url = reverse_lazy('dashboard:reels')
    is_reel = True


class VideoCommentDeleteAdminView(DashboardView, View):
    """Admin-only delete for a video comment. POST-only — no confirm
    page since it's a one-click action from the video edit screen."""
    def post(self, request, video_id, comment_id):
        deleted, _ = VideoComment.objects.filter(
            pk=comment_id, video_id=video_id
        ).delete()
        if deleted:
            messages.success(request, 'Comment deleted.')
        else:
            messages.error(request, 'Comment not found.')
        return redirect('dashboard:video-edit', pk=video_id)


class VideoDeleteView(DashboardView, DeleteView):
    model = Video
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:videos')
    is_reel = False

    def get_queryset(self):
        return super().get_queryset().filter(is_reel=self.is_reel)

    def form_valid(self, form):
        # Best-effort delete from Bunny.
        try:
            bunny.delete_video(self.object.bunny_video_guid)
        except Exception:
            pass
        messages.success(
            self.request,
            'Reel deleted.' if self.is_reel else 'Video deleted.',
        )
        return super().form_valid(form)


class ReelDeleteView(VideoDeleteView):
    success_url = reverse_lazy('dashboard:reels')
    is_reel = True


# --------------------------------------------------------------------------- 
# Rewards
# ---------------------------------------------------------------------------

class RewardsView(DashboardView, ListView):
    model = RewardLedger
    template_name = 'dashboard/rewards.html'
    paginate_by = 30
    context_object_name = 'entries'

    def get_queryset(self):
        return RewardLedger.objects.select_related('user', 'created_by').order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['total_issued'] = RewardLedger.objects.filter(points__gt=0).aggregate(
            t=Sum('points'),
        )['t'] or 0
        ctx['total_redeemed'] = abs(RewardLedger.objects.filter(points__lt=0).aggregate(
            t=Sum('points'),
        )['t'] or 0)
        return ctx


class RewardsGrantForm(forms.Form):
    user_email = forms.EmailField()
    points = forms.IntegerField(help_text='Use negative to deduct.')
    description = forms.CharField(max_length=200)


class RewardsGrantView(DashboardView, View):
    def post(self, request):
        form = RewardsGrantForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Invalid input.')
            return redirect('dashboard:rewards')

        try:
            user = User.objects.get(email__iexact=form.cleaned_data['user_email'])
        except User.DoesNotExist:
            messages.error(request, 'No user with that email.')
            return redirect('dashboard:rewards')

        points = form.cleaned_data['points']
        description = form.cleaned_data['description']

        # 1. Local audit trail in the Django ledger.
        ledger_entry = RewardLedger.objects.create(
            user=user,
            points=points,
            source=RewardLedger.SOURCE_MANUAL,
            description=description,
            created_by=request.user,
        )

        # 2. Sync to WordPress via the bridge so WPS / the mobile app see
        # the new balance immediately. wp_client.award_points routes to
        # `wps-add-par-points/user` for positive deltas and
        # `wps-remove-par-points/user` for negative deltas, AND clears the
        # 45-second balance cache, AND populates the WPS points log so the
        # Activity tab on the user's Card screen lights up with the entry.
        if user.wp_user_id:
            try:
                from apps.rewards import wp_client
                wp_client.award_points(
                    wp_user_id=user.wp_user_id,
                    delta=points,
                    source=description or 'admin grant',
                    reference_id=f'admin_grant_{ledger_entry.id}',
                )
                messages.success(
                    request,
                    f'Adjusted {user.email} by {points:+d} points (synced to WP).'
                )
            except Exception as exc:
                logger.exception('WP sync failed on admin grant')
                messages.warning(
                    request,
                    f'Logged locally but WP sync failed: {exc}. Retry once the bridge is reachable.'
                )
        else:
            messages.success(
                request,
                f'Adjusted {user.email} by {points:+d} points (Django ledger only — no WP user id).'
            )
        return redirect('dashboard:rewards')


# --------------------------------------------------------------------------- 
# Users
# ---------------------------------------------------------------------------

def _fetch_user_balances(users) -> dict:
    """Fetch WP glow-coin balances for a list of AppUser objects in
    parallel, returning {user.pk: balance_int_or_None}.

    Uses wp_client.get_user_summary with its 45-second cache, so warm
    users come back instantly. Cold-cache misses each cost a HTTP
    round-trip to WP via the bridge — we cap the pool to keep page
    loads bounded.
    """
    from concurrent.futures import ThreadPoolExecutor
    from apps.rewards import wp_client

    def fetch(user):
        if not user.wp_user_id:
            return user.pk, None
        try:
            summary = wp_client.get_user_summary(user.wp_user_id)
            return user.pk, int(summary.get('total_points') or 0)
        except Exception:
            return user.pk, None

    if not users:
        return {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        return dict(ex.map(fetch, users))


class UserListView(DashboardView, ListView):
    model = User
    template_name = 'dashboard/users.html'
    paginate_by = 30
    context_object_name = 'users'

    # Cap the in-memory list when sorting by glow coins so a user-base
    # of 10k doesn't try to fetch every balance for one page.
    _GLOW_SORT_CAP = 500

    def get_queryset(self):
        qs = User.objects.filter(is_dashboard_admin=False)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        tier = self.request.GET.get('tier', '').strip()
        if tier:
            qs = qs.filter(tier=tier)

        sort = self.request.GET.get('sort', 'recent')
        if sort == 'name':
            return qs.order_by('first_name', 'last_name', 'email')
        if sort == '-name':
            return qs.order_by('-first_name', '-last_name', '-email')
        if sort in ('tier', '-tier'):
            from django.db.models import Case, When, IntegerField, Value
            qs = qs.annotate(
                tier_rank=Case(
                    When(tier='Silver', then=Value(1)),
                    When(tier='Gold', then=Value(2)),
                    When(tier='Platinum', then=Value(3)),
                    When(tier='Titanium', then=Value(4)),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            return qs.order_by(
                '-tier_rank' if sort == '-tier' else 'tier_rank',
                'first_name',
            )
        if sort in ('glow', '-glow'):
            # Glow balance lives on WP, not in the DB — we have to fetch
            # it for every filtered user, sort in Python, and return a
            # list (Django paginators accept lists too).
            users = list(qs.order_by('-date_joined')[: self._GLOW_SORT_CAP])
            balances = _fetch_user_balances(users)
            for u in users:
                u.glow_coins = balances.get(u.pk)
            users.sort(
                key=lambda u: (u.glow_coins is None, u.glow_coins or 0),
                reverse=(sort == '-glow'),
            )
            return users
        # default: most recently joined first
        return qs.order_by('-date_joined')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['active_tier'] = self.request.GET.get('tier', '')
        ctx['active_sort'] = self.request.GET.get('sort', 'recent')

        # Counts per tier across the full user base.
        base = User.objects.filter(is_dashboard_admin=False)
        counts = {row['tier']: row['n']
                  for row in base.values('tier').annotate(n=Count('id'))}
        ctx['tier_counts'] = [
            {'value': value, 'label': label, 'count': counts.get(value, 0)}
            for value, label in User.TIER_CHOICES
        ]
        ctx['total_count'] = base.count()
        ctx['tier_choices'] = User.TIER_CHOICES

        # Attach glow coin balances to the visible page. When sort=glow
        # the balances are already on the user objects from get_queryset,
        # so we skip the fetch and just preserve them.
        users_on_page = list(ctx.get('users') or [])
        if ctx['active_sort'] not in ('glow', '-glow'):
            balances = _fetch_user_balances(users_on_page)
            for u in users_on_page:
                u.glow_coins = balances.get(u.pk)

        return ctx


class UserDetailView(DashboardView, DetailView):
    model = User
    template_name = 'dashboard/user_detail.html'
    context_object_name = 'app_user'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Glow coin balance comes from WP (canonical) — the local Django
        # ledger only tracks Django-originated events (manual grants, quiz
        # earns) and would understate the real total. Fall back to the
        # ledger sum if the bridge is unreachable so the page never blanks.
        wp_balance = None
        if self.object.wp_user_id:
            try:
                from apps.rewards import wp_client
                summary = wp_client.get_user_summary(
                    self.object.wp_user_id, use_cache=False,
                )
                wp_balance = int(summary.get('total_points') or 0)
            except Exception:
                logger.exception('WP balance fetch failed in user detail')
        ctx['balance'] = (
            wp_balance if wp_balance is not None
            else RewardLedger.balance_for(self.object)
        )
        ctx['balance_source'] = 'wp' if wp_balance is not None else 'ledger'
        ctx['ledger'] = self.object.reward_entries.order_by('-created_at')[:30]
        ctx['submissions'] = self.object.quiz_submissions.select_related(
            'quiz', 'primary_result',
        )[:20]
        ctx['tier_choices'] = User.TIER_CHOICES
        return ctx


# ---------------------------------------------------------------------------
# Membership — tier overview + card-number directory
# ---------------------------------------------------------------------------

class MembershipView(DashboardView, ListView):
    """Membership card directory — every app user with their tier + 12-digit
    membership number. Has tier-count stat cards at the top and tier/search
    filters."""
    template_name = 'dashboard/membership.html'
    paginate_by = 50
    context_object_name = 'users'

    def get_queryset(self):
        qs = User.objects.filter(
            is_dashboard_admin=False,
            wp_user_id__isnull=False,
        ).order_by('-date_joined')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(card_number_prefix__icontains=q)
            )
        tier = self.request.GET.get('tier', '').strip()
        if tier:
            qs = qs.filter(tier=tier)
        return qs

    def get_context_data(self, **kwargs):
        from apps.accounts.models import TierRule
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        ctx['active_tier'] = self.request.GET.get('tier', '')
        # Counts per tier across the whole user base (not just current page).
        base = User.objects.filter(
            is_dashboard_admin=False, wp_user_id__isnull=False,
        )
        counts = {row['tier']: row['n']
                  for row in base.values('tier').annotate(n=Count('id'))}
        ctx['tier_counts'] = [
            {'value': value, 'label': label, 'count': counts.get(value, 0)}
            for value, label in User.TIER_CHOICES
        ]
        ctx['total_members'] = base.count()
        ctx['tier_choices'] = User.TIER_CHOICES
        # Tier rules sorted by min_spent so Silver→Gold→Platinum→Titanium.
        ctx['tier_rules'] = list(
            TierRule.objects.all().order_by('is_invite_only', 'min_spent')
        )
        return ctx


class TierRuleUpdateView(DashboardView, View):
    """POST /dashboard/membership/tier-rules/ — bulk-update the tier
    rule rows from the Membership page editor.

    The form posts `rule_<id>_min_spent` and `rule_<id>_invite` for
    every TierRule. We update each row that exists, ignore unknown
    keys, and redirect back to /membership/.
    """

    def post(self, request):
        from apps.accounts.models import TierRule
        from decimal import Decimal, InvalidOperation
        updated = 0
        for rule in TierRule.objects.all():
            min_key = f'rule_{rule.id}_min_spent'
            invite_key = f'rule_{rule.id}_invite'
            label_key = f'rule_{rule.id}_card_label_subtitle'
            perks_key = f'rule_{rule.id}_perks_description'
            keys = (min_key, invite_key, label_key, perks_key)
            if not any(k in request.POST for k in keys):
                continue
            raw_min = (request.POST.get(min_key) or '0').strip() or '0'
            try:
                min_spent = Decimal(raw_min)
            except InvalidOperation:
                messages.error(request, f'Invalid amount for {rule.tier}.')
                continue
            invite = request.POST.get(invite_key) == 'on'
            label = (request.POST.get(label_key) or '').strip()
            perks = (request.POST.get(perks_key) or '').strip()
            changed = False
            if rule.min_spent != min_spent:
                rule.min_spent = min_spent
                changed = True
            if rule.is_invite_only != invite:
                rule.is_invite_only = invite
                changed = True
            if rule.card_label_subtitle != label:
                rule.card_label_subtitle = label
                changed = True
            if rule.perks_description != perks:
                rule.perks_description = perks
                changed = True
            if changed:
                rule.save()
                updated += 1
        if updated:
            messages.success(request, f'Updated {updated} tier rule(s).')
        else:
            messages.info(request, 'No changes.')
        return redirect('dashboard:membership')


class UserSpendingSyncView(DashboardView, View):
    """POST /dashboard/users/<pk>/sync-spending/ — pull the user's
    WooCommerce spending from the bridge plugin and re-evaluate
    membership tier."""

    def post(self, request, pk):
        from apps.accounts import spending as spending_service
        user = get_object_or_404(User, pk=pk)
        if not user.wp_user_id:
            messages.error(request, 'User has no wp_user_id — sync rewards first.')
            return redirect('dashboard:user-detail', pk=user.pk)
        previous_tier = user.tier
        result = spending_service.sync_user_spending(user)
        if result is None:
            messages.error(request, 'Bridge call failed — check the Django logs.')
        else:
            user.refresh_from_db()
            msg = f"Synced: ${user.total_spent} ({result.get('order_count', 0)} orders)."
            if user.tier != previous_tier:
                msg += f' Tier: {previous_tier} → {user.tier}.'
            messages.success(request, msg)
        return redirect('dashboard:user-detail', pk=user.pk)


class MembershipSyncAllView(DashboardView, View):
    """POST /dashboard/membership/sync-all/ — pull spending for every
    user with a wp_user_id (skipping admin accounts), in parallel."""

    def post(self, request):
        from apps.accounts import spending as spending_service
        from concurrent.futures import ThreadPoolExecutor
        users = list(
            User.objects
            .filter(is_dashboard_admin=False, wp_user_id__isnull=False)
        )
        if not users:
            messages.info(request, 'No users with wp_user_id to sync.')
            return redirect('dashboard:membership')

        synced = 0
        upgrades = 0

        def _do(u):
            nonlocal synced, upgrades
            prev = u.tier
            res = spending_service.sync_user_spending(u)
            if res is not None:
                synced += 1
                u.refresh_from_db()
                if u.tier != prev:
                    upgrades += 1

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(_do, users))

        messages.success(
            request,
            f'Synced {synced}/{len(users)} users. {upgrades} tier change(s).',
        )
        return redirect('dashboard:membership')


class UserTierUpdateView(DashboardView, View):
    """POST /dashboard/users/<pk>/tier/ — change a user's membership tier.
    Posts a `tier` field; redirects to user detail with a flash message."""

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        new_tier = request.POST.get('tier', '').strip()
        valid_tiers = dict(User.TIER_CHOICES)
        if new_tier not in valid_tiers:
            messages.error(request, 'Invalid tier value.')
        else:
            previous = user.tier
            user.tier = new_tier
            user.save(update_fields=['tier'])
            if previous != new_tier:
                messages.success(
                    request,
                    f'{user.display_name_or_email}: {previous} → {new_tier}.',
                )
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('dashboard:user-detail', pk=user.pk)


# ---------------------------------------------------------------------------
# Stats — aggregate metrics for videos, reels, articles
# ---------------------------------------------------------------------------

class StatsView(DashboardView, TemplateView):
    """Read-only stats dashboard.

    Surfaces:
      - Top-line counters: total views per content type, plus 7-day
        and 30-day windows.
      - Top 10 lists for videos, reels, and articles by view count
        (with avg watched %, completion rate for videos/reels).
      - 30-day daily-views sparkline data for each type.

    All aggregations run against view_events tables — VideoView and
    ArticleView — which the app POSTs to from the player + article
    detail screens.
    """
    template_name = 'dashboard/stats.html'

    def get_context_data(self, **kwargs):
        import json
        ctx = super().get_context_data(**kwargs)
        now = timezone.now()
        d7 = now - timezone.timedelta(days=7)
        d30 = now - timezone.timedelta(days=30)

        video_views = VideoView.objects.filter(is_reel=False)
        reel_views = VideoView.objects.filter(is_reel=True)
        article_views = ArticleView.objects.all()
        ebook_downloads = EbookDownload.objects.all()

        def _counts(qs):
            return {
                'all': qs.count(),
                'd7': qs.filter(created_at__gte=d7).count(),
                'd30': qs.filter(created_at__gte=d30).count(),
            }

        # List of cards the template iterates. Tuple shape is fixed so
        # it doesn't need any custom dict-access filters. Ebook downloads
        # count alongside view events — same shape, different verb.
        v = _counts(video_views)
        r = _counts(reel_views)
        a = _counts(article_views)
        e = _counts(ebook_downloads)
        ctx['totals_cards'] = [
            ('Videos', v['all'], v['d7'], v['d30']),
            ('Reels', r['all'], r['d7'], r['d30']),
            ('Articles', a['all'], a['d7'], a['d30']),
            ('Ebook downloads', e['all'], e['d7'], e['d30']),
        ]

        # Unique users (signed-in only — guests are NULL in user_id).
        ctx['unique_users_30d'] = (
            video_views.filter(created_at__gte=d30, user__isnull=False)
            .values('user_id').distinct().count()
            +
            article_views.filter(created_at__gte=d30, user__isnull=False)
            .values('user_id').distinct().count()
            +
            ebook_downloads.filter(created_at__gte=d30, user__isnull=False)
            .values('user_id').distinct().count()
        )

        # Top videos / reels / articles / ebooks by activity in 30d.
        ctx['top_videos'] = self._top_videos(is_reel=False, since=d30)
        ctx['top_reels'] = self._top_videos(is_reel=True, since=d30)
        ctx['top_articles'] = list(
            Article.objects.annotate(
                view_count=Count(
                    'view_events',
                    filter=Q(view_events__created_at__gte=d30),
                ),
            ).filter(view_count__gt=0).order_by('-view_count')[:10]
            .values('id', 'title', 'slug', 'view_count')
        )
        ctx['top_ebooks'] = list(
            Ebook.objects.annotate(
                download_count_window=Count(
                    'download_events',
                    filter=Q(download_events__created_at__gte=d30),
                ),
            ).filter(download_count_window__gt=0)
             .order_by('-download_count_window')[:10]
             .values('id', 'title', 'slug', 'is_members_only',
                     'download_count_window')
        )

        # Sparkline data — one (label, json_string) tuple per type.
        ctx['daily_series'] = [
            ('Videos', json.dumps(self._daily_counts(video_views, d30, now))),
            ('Reels', json.dumps(self._daily_counts(reel_views, d30, now))),
            ('Articles', json.dumps(self._daily_counts(article_views, d30, now))),
            ('Ebook downloads',
             json.dumps(self._daily_counts(ebook_downloads, d30, now))),
        ]

        return ctx

    @staticmethod
    def _top_videos(is_reel: bool, since):
        """Top 10 videos/reels by view count in the window, with avg
        watched-% and completion rate."""
        from django.db.models import Avg, FloatField, ExpressionWrapper
        rows = (
            Video.objects.filter(is_reel=is_reel)
            .annotate(
                view_count=Count(
                    'view_events',
                    filter=Q(view_events__created_at__gte=since),
                ),
                avg_seconds=Avg(
                    'view_events__seconds_watched',
                    filter=Q(view_events__created_at__gte=since),
                ),
                completed_count=Count(
                    'view_events',
                    filter=Q(
                        view_events__created_at__gte=since,
                        view_events__completed=True,
                    ),
                ),
            )
            .filter(view_count__gt=0)
            .order_by('-view_count')[:10]
        )
        out = []
        for v in rows:
            duration = v.duration_seconds or 0
            avg_pct = None
            if duration and v.avg_seconds:
                avg_pct = min(100, round((v.avg_seconds / duration) * 100))
            completion_pct = None
            if v.view_count:
                completion_pct = round(
                    (v.completed_count / v.view_count) * 100
                )
            out.append({
                'id': v.id,
                'title': v.title,
                'is_reel': v.is_reel,
                'view_count': v.view_count,
                'duration_seconds': duration,
                'avg_seconds': round(v.avg_seconds or 0),
                'avg_pct': avg_pct,
                'completed_count': v.completed_count,
                'completion_pct': completion_pct,
            })
        return out

    @staticmethod
    def _daily_counts(qs, since, now):
        """Returns a list of {date, count} dicts, one per day in the
        window (zero-filled), suitable for a sparkline."""
        from django.db.models.functions import TruncDate
        agg = (
            qs.filter(created_at__gte=since)
            .annotate(day=TruncDate('created_at'))
            .values('day')
            .annotate(c=Count('id'))
            .order_by('day')
        )
        by_day = {row['day']: row['c'] for row in agg}
        out = []
        cursor = since.date()
        end = now.date()
        while cursor <= end:
            out.append({
                'date': cursor.isoformat(),
                'count': by_day.get(cursor, 0),
            })
            cursor += timezone.timedelta(days=1)
        return out


# ---------------------------------------------------------------------------
# Settings — env config + Skin AI per-tier rules in a single page
# ---------------------------------------------------------------------------

# Sensible defaults seeded on first visit to the Settings page so the
# admin sees a populated Skin AI table instead of an empty section.
_SKIN_AI_DEFAULTS = [
    # (tier value, free scans, period, coin cost, unlimited?)
    ('none',     0, 'week', 50, False),
    ('Silver',   3, 'week', 50, False),
    ('Gold',     5, 'week', 50, False),
    ('Platinum', 7, 'week', 30, False),
    ('Titanium', 0, 'week',  0, True),
]


class SettingsView(DashboardView, TemplateView):
    """Combined Settings page: read-only environment config + editable
    Skin AI per-tier quota / pricing rules. The Skin AI section auto-
    seeds the 5 default rows the first time an admin lands here."""
    template_name = 'dashboard/settings.html'

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        from apps.skinai.models import SkinAiTierConfig, PERIOD_CHOICES
        ctx = super().get_context_data(**kwargs)
        ctx['env'] = {
            'WordPress base URL': dj_settings.WORDPRESS_BASE_URL,
            'Bunny Stream library ID': dj_settings.BUNNY_STREAM_LIBRARY_ID or '(not set)',
            'Bunny Stream API key': '••••' if dj_settings.BUNNY_STREAM_API_KEY else '(not set)',
            'Bunny Stream CDN hostname': dj_settings.BUNNY_STREAM_CDN_HOSTNAME or '(default mediadelivery.net)',
            'Debug mode': dj_settings.DEBUG,
            'Time zone': dj_settings.TIME_ZONE,
        }

        # Lazy seed — only runs when there are zero rows. Idempotent
        # after that; admin edits / deletes are preserved.
        if not SkinAiTierConfig.objects.exists():
            for tier, free, period, cost, unlim in _SKIN_AI_DEFAULTS:
                SkinAiTierConfig.objects.create(
                    tier=tier,
                    free_scans_per_period=free,
                    period_unit=period,
                    coin_cost_per_scan=cost,
                    unlimited_free=unlim,
                )
        order = {t: i for i, (t, *_) in enumerate(_SKIN_AI_DEFAULTS)}
        ctx['skin_ai_rules'] = sorted(
            SkinAiTierConfig.objects.all(),
            key=lambda r: order.get(r.tier, 99),
        )
        ctx['skin_ai_period_choices'] = PERIOD_CHOICES
        return ctx


class SkinAiSettingsUpdateView(DashboardView, View):
    """POST handler for the Skin AI section of the Settings page.

    The form posts `rule_<id>_<field>` per row. We update each row
    that actually changed; missing keys are ignored. Redirects back
    to the unified Settings page with a flash message.
    """

    def post(self, request):
        from apps.skinai.models import SkinAiTierConfig, PERIOD_CHOICES
        valid_periods = {p[0] for p in PERIOD_CHOICES}
        changed = 0
        for rule in SkinAiTierConfig.objects.all():
            prefix = f'rule_{rule.id}_'
            keys = (
                prefix + 'free_scans_per_period',
                prefix + 'period_unit',
                prefix + 'coin_cost_per_scan',
                prefix + 'unlimited_free',
            )
            if not any(k in request.POST for k in keys):
                continue

            try:
                free = int(request.POST.get(prefix + 'free_scans_per_period') or '0')
                cost = int(request.POST.get(prefix + 'coin_cost_per_scan') or '0')
            except ValueError:
                messages.error(
                    request,
                    f'{rule.get_tier_display()}: numbers must be whole.',
                )
                continue
            if free < 0 or cost < 0:
                messages.error(
                    request,
                    f'{rule.get_tier_display()}: values can’t be negative.',
                )
                continue

            period = (request.POST.get(prefix + 'period_unit') or '').strip()
            if period not in valid_periods:
                period = rule.period_unit
            unlimited = request.POST.get(prefix + 'unlimited_free') == 'on'

            dirty = False
            if rule.free_scans_per_period != free:
                rule.free_scans_per_period = free
                dirty = True
            if rule.coin_cost_per_scan != cost:
                rule.coin_cost_per_scan = cost
                dirty = True
            if rule.period_unit != period:
                rule.period_unit = period
                dirty = True
            if rule.unlimited_free != unlimited:
                rule.unlimited_free = unlimited
                dirty = True
            if dirty:
                rule.save()
                changed += 1

        if changed:
            messages.success(request, f'Updated {changed} Skin AI rule(s).')
        else:
            messages.info(request, 'No Skin AI changes.')
        return redirect('dashboard:settings')


# ---------------------------------------------------------------------------
# Skin AI — results browser (per-user scan history)
# ---------------------------------------------------------------------------

class SkinAiClearProductsCacheView(DashboardView, View):
    """POST /dashboard/skin-ai/clear-products-cache/ — drop the cached
    WooCommerce product list so the next recommendation call refetches
    from `wp-json/alluora/v1/products`. Use after a shop update so the
    in-app carousel + admin scan-detail pick up the changes before the
    1-hour TTL expires."""

    def post(self, request):
        from django.core.cache import cache
        from apps.skinai.recommendations import CACHE_KEY
        cache.delete(CACHE_KEY)
        messages.success(
            request,
            'Skin AI product cache cleared. Next scan will refetch '
            'the catalog from WordPress.',
        )
        return redirect(request.POST.get('next') or 'dashboard:settings')


class SkinAiRefreshTierAvgView(DashboardView, View):
    """POST /dashboard/skin-ai/refresh-tier-averages/ — recompute the
    per-tier benchmarking aggregation now instead of waiting out the
    SKINAI_TIER_AVG_CACHE_TTL window. Reports back whether the
    feature is currently dormant (below the user-count floor) or
    active. Read-only otherwise."""

    def post(self, request):
        from django.conf import settings as dj_settings
        from apps.skinai import tier_averages
        result = tier_averages.tier_averages(force_refresh=True)
        if result:
            messages.success(
                request,
                'Skin AI tier averages refreshed. '
                f'Active for {len(result)} tier(s): '
                + ', '.join(sorted(result.keys())),
            )
        else:
            floor = getattr(dj_settings, 'SKINAI_TIER_AVG_MIN_USERS', 10)
            messages.info(
                request,
                'Tier averages computed but suppressed: at least one '
                f'tier has fewer than {floor} users with recent scans. '
                'Set SKINAI_TIER_AVG_MIN_USERS lower if you want to '
                'flip the feature on now.',
            )
        return redirect(request.POST.get('next') or 'dashboard:settings')


class SkinAiUsersView(DashboardView, ListView):
    """Lists app users who have ever run a Skin AI scan, with the
    total scan count and latest overall score. Admins click through to
    a per-user detail page that shows individual scans."""
    template_name = 'dashboard/skin_ai_users.html'
    context_object_name = 'users'
    paginate_by = 50

    def get_queryset(self):
        q = self.request.GET.get('q', '').strip()
        users = (
            User.objects
            .filter(skin_analyses__isnull=False)
            .annotate(scan_count=Count('skin_analyses'))
            .distinct()
            .order_by('-date_joined')
        )
        if q:
            users = users.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )
        return users

    def get_context_data(self, **kwargs):
        from apps.skinai.models import SkinAnalysis
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        # Per-user latest-scan map, but scoped to the page that's
        # actually rendering — no point pulling every SkinAnalysis row
        # for users not on this paginated screen. Previous version
        # walked the whole table to build the dict.
        page_users = ctx.get('users') or []
        page_user_ids = [u.id for u in page_users]
        latest_by_user = {}
        if page_user_ids:
            latest_rows = (
                SkinAnalysis.objects
                .filter(user_id__in=page_user_ids)
                .order_by('user_id', '-created_at')
                .only(
                    'id', 'user_id', 'created_at', 'overall_score',
                    'skin_age',
                )
            )
            for s in latest_rows:
                if s.user_id not in latest_by_user:
                    latest_by_user[s.user_id] = s
        ctx['latest_by_user'] = latest_by_user
        ctx['total_visible'] = SkinAnalysis.objects.count()
        return ctx


class SkinAiUserDetailView(DashboardView, DetailView):
    """One app user's Skin AI scan history. Supports per-row delete and
    bulk actions (clear selected / clear all) — all of which hard-delete
    the rows from the database."""
    template_name = 'dashboard/skin_ai_user_detail.html'
    context_object_name = 'app_user'
    queryset = User.objects.all()

    def get_context_data(self, **kwargs):
        from apps.skinai.models import SkinAnalysis
        ctx = super().get_context_data(**kwargs)
        ctx['scans'] = (
            SkinAnalysis.objects
            .filter(user=self.object)
            .order_by('-created_at')
        )
        return ctx


class SkinAiAnalysisDetailView(DashboardView, DetailView):
    """Full breakdown of a single SkinAnalysis row, mirroring the
    in-app result screen layout but rendered server-side."""
    template_name = 'dashboard/skin_ai_analysis_detail.html'
    context_object_name = 'analysis'

    def get_queryset(self):
        from apps.skinai.models import SkinAnalysis
        return SkinAnalysis.objects.all()

    def get_context_data(self, **kwargs):
        from apps.skinai import insights as skinai_insights
        from apps.skinai import recommendations as skinai_rec
        ctx = super().get_context_data(**kwargs)
        a = self.object
        primary = [
            ('Hydration', a.hydration_score),
            ('Pores', a.pores_score),
            ('Wrinkles', a.wrinkles_score),
            ('Redness', a.redness_score),
            ('Spots', a.spots_score),
        ]
        extended = [
            ('Pigmentation', getattr(a, 'pigmentation_score', 0)),
            ('Acne / breakouts', getattr(a, 'acne_score', 0)),
            ('Dark circles', getattr(a, 'dark_circles_score', 0)),
            ('Eyebags', getattr(a, 'eyebags_score', 0)),
            ('White spots', getattr(a, 'white_spots_score', 0)),
        ]
        # Hide the 5 extended categories on pre-v2 rows so admins
        # don't see "0/100" placeholders for metrics that never ran.
        pipeline_v = getattr(a, 'pipeline_version', 1) or 1
        ctx['scores'] = primary + (extended if pipeline_v >= 2 else [])
        ctx['is_legacy_scan'] = pipeline_v < 2
        # Same summary / headline / body the user sees on the in-app
        # result screen, computed from the scores + the user's stored
        # primary concern. See insights.py.
        concern = getattr(a.user, 'skin_primary_concern', '') or ''
        ctx['insight'] = skinai_insights.compute(a, primary_concern=concern)
        # Same per-category breakdown rendered in the in-app result.
        ctx['insight_details'] = skinai_insights.compute_details(a)
        # Same product picks the in-app result screen would show.
        # Best-effort — swallow any WP fetch failure so the page
        # renders even if the storefront is unreachable.
        try:
            ctx['recommendations'] = skinai_rec.recommend_for_analysis(a)
        except Exception:
            ctx['recommendations'] = []
        # Pretty-print the user's tracked concerns (comma-separated
        # slug list on AppUser → " · "-joined human-readable string).
        _concern_pretty = {
            'hydration': 'Hydration',
            'aging': 'Anti-aging',
            'acne': 'Acne / breakouts',
            'brightening': 'Brightening',
            'sensitivity': 'Sensitivity',
            'pigmentation': 'Pigmentation',
            'dark_circles': 'Dark circles',
            'eyebags': 'Eyebags',
            'white_spots': 'White spots',
            'pores': 'Pores',
        }
        raw_concerns = (a.user.skin_primary_concern or '').split(',')
        labels = [
            _concern_pretty.get(s.strip(), s.strip())
            for s in raw_concerns if s.strip()
        ]
        ctx['user_concern_labels'] = ' · '.join(labels)
        return ctx


class SkinAiAnalysisOriginalView(DashboardView, View):
    """GET /dashboard/skin-ai/results/<pk>/original/ — stream the hi-res
    original JPEG. Admin-only by virtue of DashboardView's auth gate;
    the file is never published under /media/ so the URL can't be
    enumerated by guessing paths."""

    def get(self, request, pk: int):
        from apps.skinai.models import SkinAnalysis
        from django.http import FileResponse, Http404
        analysis = get_object_or_404(SkinAnalysis, pk=pk)
        if not analysis.original_photo:
            raise Http404('No hi-res original on file for this scan.')
        try:
            fh = analysis.original_photo.open('rb')
        except FileNotFoundError:
            raise Http404('Hi-res original file is missing.')
        return FileResponse(fh, content_type='image/jpeg')


class SkinAiAnalysisDeleteView(DashboardView, View):
    """POST /dashboard/skin-ai/results/<pk>/delete/ — hard-delete one
    scan. Removes the row (and its thumbnail) from the database. The
    user's app history stops showing it on next refresh."""

    def post(self, request, pk: int):
        from apps.skinai.models import SkinAnalysis
        try:
            row = SkinAnalysis.objects.get(pk=pk)
        except SkinAnalysis.DoesNotExist:
            messages.error(request, 'Scan not found.')
            return redirect('dashboard:skin-ai-users')
        user_id = row.user_id
        row.delete()
        messages.success(request, 'Scan deleted.')
        next_url = request.POST.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('dashboard:skin-ai-user-detail', pk=user_id)


class SkinAiUserBulkDeleteView(DashboardView, View):
    """POST /dashboard/skin-ai/users/<pk>/bulk-delete/ — clear-selected
    or clear-all hard delete for a single user.

    Form fields:
      action     'delete-selected' | 'clear-all'
      scan_ids   one per checked row (only used by delete-selected)
    """

    def post(self, request, pk: int):
        from apps.skinai.models import SkinAnalysis
        user = get_object_or_404(User, pk=pk)
        action = request.POST.get('action', '').strip()
        qs = SkinAnalysis.objects.filter(user=user)

        if action == 'clear-all':
            deleted, _ = qs.delete()
            if deleted:
                messages.success(
                    request,
                    f'Cleared all {deleted} scan(s) for {user.email}.',
                )
            else:
                messages.info(request, 'No scans to clear.')
        elif action == 'delete-selected':
            raw_ids = request.POST.getlist('scan_ids')
            ids = []
            for raw in raw_ids:
                try:
                    ids.append(int(raw))
                except (TypeError, ValueError):
                    continue
            if not ids:
                messages.info(request, 'No scans selected.')
            else:
                deleted, _ = qs.filter(pk__in=ids).delete()
                messages.success(request, f'Deleted {deleted} scan(s).')
        else:
            messages.error(request, 'Unknown bulk action.')

        return redirect('dashboard:skin-ai-user-detail', pk=user.pk)
