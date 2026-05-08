"""Custom admin dashboard.

Server-rendered with Django templates + Tailwind (CDN) + Alpine.js for the
interactive bits. Uses Django's session auth (NOT the WordPress cookie auth
the mobile app uses).

Only users with is_dashboard_admin=True can access. The bootstrap admin
created by `manage.py create_admin` has this flag set automatically.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum, Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView,
)

from apps.content.models import Article, ContentCategory
from apps.videos.models import Video, VideoCollection
from apps.videos import bunny
from apps.rewards.models import RewardLedger, Badge
from apps.quiz.models import Submission

User = get_user_model()


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
                  'cover_image_url', 'status', 'is_featured')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'summary': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
            'body': forms.Textarea(attrs={'class': 'form-input font-mono', 'rows': 16}),
            'cover_image_url': forms.URLInput(attrs={'class': 'form-input'}),
            'category': forms.Select(attrs={'class': 'form-input'}),
            'status': forms.Select(attrs={'class': 'form-input'}),
        }


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
# Videos
# ---------------------------------------------------------------------------

class VideoMetaForm(forms.ModelForm):
    """Used after upload to edit metadata. Upload itself happens via the
    /api/v1/videos/admin/* endpoints with TUS to Bunny directly."""
    class Meta:
        model = Video
        fields = ('title', 'description', 'collection', 'is_featured', 'is_published')
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
            'collection': forms.Select(attrs={'class': 'form-input'}),
        }


class VideoListView(DashboardView, ListView):
    model = Video
    template_name = 'dashboard/videos.html'
    paginate_by = 20
    context_object_name = 'videos'

    def get_queryset(self):
        return Video.objects.select_related('collection').order_by('-created_at')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['bunny_configured'] = bunny.is_configured()
        ctx['collections'] = VideoCollection.objects.all()
        return ctx


class VideoCreateView(DashboardView, TemplateView):
    """Renders the upload page. Actual upload uses the JSON API + tus-js-client."""
    template_name = 'dashboard/video_create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['bunny_configured'] = bunny.is_configured()
        ctx['collections'] = VideoCollection.objects.all()
        return ctx


class VideoEditView(DashboardView, UpdateView):
    model = Video
    form_class = VideoMetaForm
    template_name = 'dashboard/video_edit.html'
    success_url = reverse_lazy('dashboard:videos')

    def form_valid(self, form):
        messages.success(self.request, 'Video updated.')
        return super().form_valid(form)


class VideoDeleteView(DashboardView, DeleteView):
    model = Video
    template_name = 'dashboard/confirm_delete.html'
    success_url = reverse_lazy('dashboard:videos')

    def form_valid(self, form):
        # Best-effort delete from Bunny.
        try:
            bunny.delete_video(self.object.bunny_video_guid)
        except Exception:
            pass
        messages.success(self.request, 'Video deleted.')
        return super().form_valid(form)


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

        RewardLedger.objects.create(
            user=user,
            points=form.cleaned_data['points'],
            source=RewardLedger.SOURCE_MANUAL,
            description=form.cleaned_data['description'],
            created_by=request.user,
        )
        messages.success(request, f'Adjusted {user.email} by {form.cleaned_data["points"]:+d} points.')
        return redirect('dashboard:rewards')


# --------------------------------------------------------------------------- 
# Users
# ---------------------------------------------------------------------------

class UserListView(DashboardView, ListView):
    model = User
    template_name = 'dashboard/users.html'
    paginate_by = 30
    context_object_name = 'users'

    def get_queryset(self):
        qs = User.objects.filter(is_dashboard_admin=False).order_by('-date_joined')
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['q'] = self.request.GET.get('q', '')
        return ctx


class UserDetailView(DashboardView, DetailView):
    model = User
    template_name = 'dashboard/user_detail.html'
    context_object_name = 'app_user'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['balance'] = RewardLedger.balance_for(self.object)
        ctx['ledger'] = self.object.reward_entries.order_by('-created_at')[:30]
        ctx['submissions'] = self.object.quiz_submissions.select_related(
            'quiz', 'primary_result',
        )[:20]
        return ctx


# --------------------------------------------------------------------------- 
# Settings (read-only display of current env config)
# ---------------------------------------------------------------------------

class SettingsView(DashboardView, TemplateView):
    template_name = 'dashboard/settings.html'

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx['env'] = {
            'WordPress base URL': dj_settings.WORDPRESS_BASE_URL,
            'Bunny Stream library ID': dj_settings.BUNNY_STREAM_LIBRARY_ID or '(not set)',
            'Bunny Stream API key': '••••' if dj_settings.BUNNY_STREAM_API_KEY else '(not set)',
            'Bunny Stream CDN hostname': dj_settings.BUNNY_STREAM_CDN_HOSTNAME or '(default mediadelivery.net)',
            'Debug mode': dj_settings.DEBUG,
            'Time zone': dj_settings.TIME_ZONE,
        }
        return ctx
