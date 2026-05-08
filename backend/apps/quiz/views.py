"""Quiz API.

  GET /api/v1/quiz/{slug}/                 fetch quiz with questions/options
  POST /api/v1/quiz/{slug}/submit/         submit answers, get result type back
  GET /api/v1/quiz/submissions/            user's past submissions
"""
from collections import defaultdict
from rest_framework import serializers, generics, permissions, status
from rest_framework.response import Response
from .models import Quiz, Question, Option, ResultType, Submission


class OptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ('id', 'text', 'sort_order')


class QuestionSerializer(serializers.ModelSerializer):
    options = OptionSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = ('id', 'text', 'sort_order', 'options')


class ResultTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResultType
        fields = ('id', 'slug', 'name', 'summary', 'long_description', 'image_url')


class QuizDetailSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ('id', 'slug', 'name', 'intro', 'questions')


class SubmissionSerializer(serializers.ModelSerializer):
    primary_result = ResultTypeSerializer(read_only=True)
    quiz_name = serializers.CharField(source='quiz.name', read_only=True)
    quiz_slug = serializers.CharField(source='quiz.slug', read_only=True)

    class Meta:
        model = Submission
        fields = (
            'id', 'quiz_slug', 'quiz_name',
            'primary_result', 'score_breakdown', 'submitted_at',
        )


class QuizDetailView(generics.RetrieveAPIView):
    """GET /api/v1/quiz/{slug}/"""
    queryset = Quiz.objects.filter(is_active=True).prefetch_related(
        'questions__options', 'result_types',
    )
    serializer_class = QuizDetailSerializer
    lookup_field = 'slug'
    permission_classes = [permissions.AllowAny]


class QuizSubmitView(generics.GenericAPIView):
    """POST /api/v1/quiz/{slug}/submit/

    Body: { "answers": [option_id, option_id, ...] }
    Returns: SubmissionSerializer with computed result type.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, slug):
        try:
            quiz = Quiz.objects.get(slug=slug, is_active=True)
        except Quiz.DoesNotExist:
            return Response({'detail': 'Quiz not found.'}, status=status.HTTP_404_NOT_FOUND)

        option_ids = request.data.get('answers') or []
        if not isinstance(option_ids, list) or not option_ids:
            return Response(
                {'detail': 'Provide a non-empty list of option ids in `answers`.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        options = list(Option.objects.filter(
            id__in=option_ids,
            question__quiz=quiz,
        ).select_related('question'))

        if len(options) != len(set(option_ids)):
            return Response(
                {'detail': 'Some option ids are invalid for this quiz.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Compute per-result-type scores.
        scores = defaultdict(int)
        for opt in options:
            for slug_key, weight in (opt.weights or {}).items():
                try:
                    scores[slug_key] += int(weight)
                except (TypeError, ValueError):
                    pass

        # Pick the highest-scoring result type that exists for this quiz.
        result_types = {rt.slug: rt for rt in quiz.result_types.all()}
        best_slug = None
        best_score = -1
        for slug_key, score in scores.items():
            if slug_key in result_types and score > best_score:
                best_slug = slug_key
                best_score = score

        primary_result = result_types.get(best_slug) if best_slug else None

        submission = Submission.objects.create(
            user=request.user,
            quiz=quiz,
            primary_result=primary_result,
            score_breakdown=dict(scores),
        )
        submission.selected_options.set(options)

        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class MySubmissionsView(generics.ListAPIView):
    """GET /api/v1/quiz/submissions/ — user's quiz history."""
    serializer_class = SubmissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Submission.objects.filter(user=self.request.user).select_related(
            'quiz', 'primary_result',
        )
