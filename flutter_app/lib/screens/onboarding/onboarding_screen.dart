import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../widgets/alluora_logo.dart';

/// The Begin page from the mockups. Cream background, soft "petal" blobs,
/// the new SVG-style logo at center, and a "Glow-Up" headline.
class OnboardingScreen extends StatelessWidget {
  const OnboardingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AlluoraColors.cream,
      body: SafeArea(
        child: Stack(
          children: [
            // Decorative petal blobs (matching the mockup).
            const Positioned(top: 120, left: -40, child: _Petal(size: 220, opacity: .35)),
            const Positioned(top: 280, right: -60, child: _Petal(size: 180, opacity: .25)),

            Column(
              children: [
                const SizedBox(height: 72),

                // Logo center
                const Expanded(
                  flex: 2,
                  child: Center(child: AlluoraLogo(size: 130)),
                ),

                // Copy
                Expanded(
                  flex: 2,
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.center,
                      mainAxisAlignment: MainAxisAlignment.start,
                      children: [
                        Text('Get your', style: AlluoraTypography.hero, textAlign: TextAlign.center),
                        Text(
                          'Glow-Up.',
                          style: AlluoraTypography.hero.copyWith(
                            fontStyle: FontStyle.italic,
                            color: AlluoraColors.primary,
                          ),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 18),
                        Text(
                          'Watch, learn and earn rewards as you transform your skin with Alluora.',
                          style: AlluoraTypography.bodyDefault.copyWith(
                            color: AlluoraColors.textSecondary,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),

                // CTAs
                Padding(
                  padding: const EdgeInsets.fromLTRB(28, 8, 28, 32),
                  child: Column(
                    children: [
                      ElevatedButton(
                        onPressed: () => context.push('/register'),
                        child: const Text('Begin'),
                      ),
                      const SizedBox(height: 12),
                      TextButton(
                        onPressed: () => context.push('/login'),
                        child: const Text('I already have an account'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Petal extends StatelessWidget {
  final double size;
  final double opacity;
  const _Petal({required this.size, this.opacity = 0.3});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: AlluoraColors.primaryLight.withValues(alpha: opacity),
      ),
    );
  }
}
