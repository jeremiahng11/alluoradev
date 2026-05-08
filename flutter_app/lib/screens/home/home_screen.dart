import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../services/auth_service.dart';
import '../../services/django_api.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _loading = true;
  Map<String, dynamic>? _djangoMe;
  List<dynamic> _featuredArticles = [];
  List<dynamic> _featuredVideos = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        DjangoApi.instance.me(),
        DjangoApi.instance.listArticles(featured: true),
        DjangoApi.instance.listVideos(featured: true),
      ]);
      if (!mounted) return;
      setState(() {
        _djangoMe = results[0] as Map<String, dynamic>?;
        _featuredArticles = results[1] as List<dynamic>;
        _featuredVideos = results[2] as List<dynamic>;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'Good morning,';
    if (h < 18) return 'Good afternoon,';
    return 'Good evening,';
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthService>().user;
    final firstName = user?['first_name'] as String? ?? '';
    final displayName = firstName.isNotEmpty ? firstName : (user?['display_name'] as String? ?? '');
    final balance = (_djangoMe?['reward_points'] as num?)?.toInt() ?? 0;

    return RefreshIndicator(
      onRefresh: _load,
      color: AlluoraColors.primary,
      child: ListView(
        padding: const EdgeInsets.only(top: 8, bottom: 24),
        children: [
          // Greeting + avatar
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 12),
            child: Row(
              children: [
                Expanded(
                  child: Text.rich(
                    TextSpan(children: [
                      TextSpan(text: '${_greeting()}\n', style: AlluoraTypography.h3.copyWith(fontStyle: FontStyle.italic)),
                      TextSpan(text: displayName, style: AlluoraTypography.h2.copyWith(fontWeight: FontWeight.w500)),
                    ]),
                  ),
                ),
                Container(
                  width: 44, height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const LinearGradient(
                      begin: Alignment.topLeft, end: Alignment.bottomRight,
                      colors: [AlluoraColors.primaryLight, AlluoraColors.primary],
                    ),
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    displayName.isNotEmpty ? displayName[0].toUpperCase() : 'A',
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                  ),
                ),
              ],
            ),
          ),

          // Points pill
          GestureDetector(
            onTap: () => context.go('/card'),
            child: Container(
              margin: const EdgeInsets.fromLTRB(20, 4, 20, 16),
              padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Colors.white, Color(0xFFFBF1E0)],
                ),
                border: Border.all(color: AlluoraColors.border),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Row(
                children: [
                  const Icon(Icons.star_outline, color: AlluoraColors.primary, size: 22),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Glow Points', style: AlluoraTypography.caption.copyWith(letterSpacing: 0.5)),
                        const SizedBox(height: 2),
                        Text('$balance pts', style: AlluoraTypography.h3),
                      ],
                    ),
                  ),
                  const Icon(Icons.chevron_right, color: AlluoraColors.textMuted),
                ],
              ),
            ),
          ),

          // Featured videos
          if (_featuredVideos.isNotEmpty) ...[
            _SectionHeader(title: 'Watch & earn', subtitle: '+5 pts per video'),
            SizedBox(
              height: 200,
              child: ListView.separated(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                scrollDirection: Axis.horizontal,
                itemCount: _featuredVideos.length,
                separatorBuilder: (_, __) => const SizedBox(width: 12),
                itemBuilder: (_, i) => _VideoCard(video: _featuredVideos[i] as Map<String, dynamic>),
              ),
            ),
            const SizedBox(height: 24),
          ],

          // Featured articles
          if (_featuredArticles.isNotEmpty) ...[
            _SectionHeader(title: 'Read', subtitle: 'Tips & rituals'),
            ..._featuredArticles.map((a) => _ArticleTile(article: a as Map<String, dynamic>)),
          ],

          // Loading or empty
          if (_loading)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 40),
              child: Center(child: CircularProgressIndicator(color: AlluoraColors.primary)),
            )
          else if (_featuredArticles.isEmpty && _featuredVideos.isEmpty)
            Padding(
              padding: const EdgeInsets.all(40),
              child: Column(
                children: [
                  const Icon(Icons.spa_outlined, size: 48, color: AlluoraColors.textMuted),
                  const SizedBox(height: 12),
                  Text('No featured content yet', style: AlluoraTypography.bodyDefault),
                  const SizedBox(height: 4),
                  Text(
                    'Check back soon for new tips and tutorials.',
                    style: AlluoraTypography.bodySmall.copyWith(color: AlluoraColors.textMuted),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  const _SectionHeader({required this.title, this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(title, style: AlluoraTypography.h3),
          const SizedBox(width: 12),
          if (subtitle != null)
            Text(
              subtitle!,
              style: AlluoraTypography.caption.copyWith(color: AlluoraColors.primary),
            ),
        ],
      ),
    );
  }
}

class _VideoCard extends StatelessWidget {
  final Map<String, dynamic> video;
  const _VideoCard({required this.video});

  @override
  Widget build(BuildContext context) {
    final thumb = video['thumbnail_url'] as String?;
    final title = video['title'] as String? ?? '';
    return Container(
      width: 240,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14),
        color: AlluoraColors.surfaceWarm,
        border: Border.all(color: AlluoraColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: thumb != null && thumb.isNotEmpty
                ? CachedNetworkImage(imageUrl: thumb, fit: BoxFit.cover, width: double.infinity)
                : Container(color: AlluoraColors.surfaceWarm, child: const Center(child: Icon(Icons.play_circle_outline, size: 44, color: AlluoraColors.textMuted))),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Text(
              title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: AlluoraTypography.bodyDefault.copyWith(fontWeight: FontWeight.w500),
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticleTile extends StatelessWidget {
  final Map<String, dynamic> article;
  const _ArticleTile({required this.article});

  @override
  Widget build(BuildContext context) {
    final cover = article['cover'] as String?;
    final title = article['title'] as String? ?? '';
    final summary = article['summary'] as String? ?? '';
    final slug = article['slug'] as String? ?? '';

    return InkWell(
      onTap: slug.isEmpty ? null : () => context.push('/articles/$slug'),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 6, 20, 14),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox(
                width: 80, height: 80,
                child: cover != null && cover.isNotEmpty
                    ? CachedNetworkImage(imageUrl: cover, fit: BoxFit.cover)
                    : Container(color: AlluoraColors.surfaceWarm, child: const Icon(Icons.article_outlined, color: AlluoraColors.textMuted)),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, style: AlluoraTypography.bodyDefault.copyWith(fontWeight: FontWeight.w500)),
                  const SizedBox(height: 4),
                  Text(summary, maxLines: 2, overflow: TextOverflow.ellipsis, style: AlluoraTypography.bodySmall.copyWith(color: AlluoraColors.textSecondary)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
