import 'package:flutter/material.dart';

import '../../services/django_api.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';

class CardScreen extends StatefulWidget {
  const CardScreen({super.key});

  @override
  State<CardScreen> createState() => _CardScreenState();
}

class _CardScreenState extends State<CardScreen> {
  bool _loading = true;
  int _balance = 0;
  List<dynamic> _badges = [];
  List<dynamic> _history = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        DjangoApi.instance.rewardsBalance(),
        DjangoApi.instance.rewardsHistory(),
      ]);
      if (!mounted) return;
      final balance = results[0] as Map<String, dynamic>;
      setState(() {
        _balance = (balance['balance'] as num?)?.toInt() ?? 0;
        _badges = (balance['badges'] as List?) ?? [];
        _history = results[1] as List<dynamic>;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AlluoraColors.cream,
      appBar: AppBar(
        title: const Text('Your Card'),
        backgroundColor: AlluoraColors.cream,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        color: AlluoraColors.primary,
        child: _loading
            ? const Center(child: CircularProgressIndicator(color: AlluoraColors.primary))
            : ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  // Membership card
                  Container(
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(20),
                      gradient: const LinearGradient(
                        begin: Alignment.topLeft, end: Alignment.bottomRight,
                        colors: [AlluoraColors.primaryDark, AlluoraColors.primary],
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Glow Card', style: AlluoraTypography.caption.copyWith(color: Colors.white70, letterSpacing: 1.2)),
                        const SizedBox(height: 8),
                        Text(
                          '$_balance pts',
                          style: AlluoraTypography.h1.copyWith(color: Colors.white, fontSize: 44),
                        ),
                        const SizedBox(height: 24),
                        Row(
                          children: [
                            Icon(Icons.workspace_premium_outlined, color: Colors.white.withValues(alpha: 0.9), size: 20),
                            const SizedBox(width: 6),
                            Text('Silver tier', style: AlluoraTypography.bodyDefault.copyWith(color: Colors.white)),
                          ],
                        ),
                      ],
                    ),
                  ),

                  if (_badges.isNotEmpty) ...[
                    const SizedBox(height: 24),
                    Text('Badges', style: AlluoraTypography.h3),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 12, runSpacing: 12,
                      children: _badges.map((b) {
                        final badge = (b as Map)['badge'] as Map?;
                        if (badge == null) return const SizedBox.shrink();
                        return Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(999),
                            border: Border.all(color: AlluoraColors.border),
                          ),
                          child: Text(badge['name'] as String? ?? '', style: AlluoraTypography.bodySmall),
                        );
                      }).toList(),
                    ),
                  ],

                  const SizedBox(height: 24),
                  Text('Activity', style: AlluoraTypography.h3),
                  const SizedBox(height: 8),
                  if (_history.isEmpty)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text(
                          'No points yet — earn by watching videos and completing the quiz.',
                          style: AlluoraTypography.bodySmall.copyWith(color: AlluoraColors.textMuted),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    )
                  else
                    ..._history.take(20).map((entry) => _LedgerRow(entry: entry as Map<String, dynamic>)),
                ],
              ),
      ),
    );
  }
}

class _LedgerRow extends StatelessWidget {
  final Map<String, dynamic> entry;
  const _LedgerRow({required this.entry});

  @override
  Widget build(BuildContext context) {
    final pts = (entry['points'] as num?)?.toInt() ?? 0;
    final desc = entry['description'] as String? ?? '';
    final source = entry['source'] as String? ?? '';
    final positive = pts >= 0;
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AlluoraColors.border),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(desc.isEmpty ? source : desc, style: AlluoraTypography.bodyDefault),
                const SizedBox(height: 2),
                Text(source, style: AlluoraTypography.caption.copyWith(color: AlluoraColors.textMuted)),
              ],
            ),
          ),
          Text(
            (positive ? '+' : '') + pts.toString() + ' pts',
            style: AlluoraTypography.bodyDefault.copyWith(
              fontWeight: FontWeight.w600,
              color: positive ? AlluoraColors.primary : AlluoraColors.textMuted,
            ),
          ),
        ],
      ),
    );
  }
}
