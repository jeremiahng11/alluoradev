import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../theme/colors.dart';

/// Bottom-nav shell — wraps the 4 main tabs from the mockup:
/// Home / Card / Shop / You.
class MainShell extends StatelessWidget {
  final Widget child;
  const MainShell({super.key, required this.child});

  static const _tabs = [
    _Tab(label: 'Home', icon: Icons.home_outlined, activeIcon: Icons.home, route: '/home'),
    _Tab(label: 'Card', icon: Icons.card_membership_outlined, activeIcon: Icons.card_membership, route: '/card'),
    _Tab(label: 'Shop', icon: Icons.shopping_bag_outlined, activeIcon: Icons.shopping_bag, route: '/shop'),
    _Tab(label: 'You', icon: Icons.person_outline, activeIcon: Icons.person, route: '/profile'),
  ];

  int _currentIndex(BuildContext context) {
    final loc = GoRouterState.of(context).matchedLocation;
    final idx = _tabs.indexWhere((t) => loc.startsWith(t.route));
    return idx >= 0 ? idx : 0;
  }

  @override
  Widget build(BuildContext context) {
    final current = _currentIndex(context);
    return Scaffold(
      body: child,
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          border: Border(top: BorderSide(color: AlluoraColors.border, width: 1)),
        ),
        child: SafeArea(
          top: false,
          child: SizedBox(
            height: 64,
            child: Row(
              children: List.generate(_tabs.length, (i) {
                final t = _tabs[i];
                final selected = i == current;
                return Expanded(
                  child: InkWell(
                    onTap: () => context.go(t.route),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          selected ? t.activeIcon : t.icon,
                          size: 24,
                          color: selected ? AlluoraColors.primary : AlluoraColors.textMuted,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          t.label,
                          style: TextStyle(
                            fontSize: 11,
                            letterSpacing: 0.5,
                            fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                            color: selected ? AlluoraColors.primary : AlluoraColors.textMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

class _Tab {
  final String label;
  final IconData icon;
  final IconData activeIcon;
  final String route;
  const _Tab({required this.label, required this.icon, required this.activeIcon, required this.route});
}
