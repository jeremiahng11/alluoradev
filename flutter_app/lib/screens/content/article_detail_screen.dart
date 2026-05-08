import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:go_router/go_router.dart';

import '../../services/django_api.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';

class ArticleDetailScreen extends StatefulWidget {
  final String slug;
  const ArticleDetailScreen({super.key, required this.slug});

  @override
  State<ArticleDetailScreen> createState() => _ArticleDetailScreenState();
}

class _ArticleDetailScreenState extends State<ArticleDetailScreen> {
  Map<String, dynamic>? _article;
  bool _loading = true;
  Object? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final result = await DjangoApi.instance.getArticle(widget.slug);
      if (!mounted) return;
      setState(() {
        _article = result;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AlluoraColors.cream,
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AlluoraColors.primary))
          : _error != null || _article == null
              ? _ErrorState(onBack: () => context.pop())
              : _ArticleBody(article: _article!),
    );
  }
}

class _ArticleBody extends StatelessWidget {
  final Map<String, dynamic> article;
  const _ArticleBody({required this.article});

  @override
  Widget build(BuildContext context) {
    final cover = article['cover'] as String? ?? '';
    final title = article['title'] as String? ?? '';
    final summary = article['summary'] as String? ?? '';
    final body = article['body'] as String? ?? '';
    final author = article['author_name'] as String? ?? '';

    return CustomScrollView(
      slivers: [
        SliverAppBar(
          expandedHeight: cover.isNotEmpty ? 240 : kToolbarHeight,
          pinned: true,
          backgroundColor: AlluoraColors.cream,
          foregroundColor: AlluoraColors.textPrimary,
          flexibleSpace: cover.isNotEmpty
              ? FlexibleSpaceBar(
                  background: CachedNetworkImage(imageUrl: cover, fit: BoxFit.cover),
                )
              : null,
        ),
        SliverPadding(
          padding: const EdgeInsets.all(20),
          sliver: SliverList.list(
            children: [
              Text(title, style: AlluoraTypography.h1),
              if (author.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text('By $author', style: AlluoraTypography.caption.copyWith(color: AlluoraColors.textMuted)),
              ],
              if (summary.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  summary,
                  style: AlluoraTypography.bodyDefault.copyWith(
                    color: AlluoraColors.textSecondary,
                    fontStyle: FontStyle.italic,
                  ),
                ),
              ],
              const SizedBox(height: 24),
              MarkdownBody(
                data: body,
                styleSheet: MarkdownStyleSheet(
                  p: AlluoraTypography.bodyDefault,
                  h1: AlluoraTypography.h2,
                  h2: AlluoraTypography.h3,
                  blockquote: AlluoraTypography.bodyDefault.copyWith(
                    fontStyle: FontStyle.italic,
                    color: AlluoraColors.textSecondary,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ErrorState extends StatelessWidget {
  final VoidCallback onBack;
  const _ErrorState({required this.onBack});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 48, color: AlluoraColors.textMuted),
            const SizedBox(height: 12),
            Text('Could not load this article', style: AlluoraTypography.h3),
            const SizedBox(height: 16),
            FilledButton(onPressed: onBack, child: const Text('Go back')),
          ],
        ),
      ),
    );
  }
}
