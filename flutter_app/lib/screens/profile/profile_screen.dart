import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../services/auth_service.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthService>().user;
    final firstName = user?['first_name'] as String? ?? '';
    final lastName = user?['last_name'] as String? ?? '';
    final email = user?['email'] as String? ?? '';
    final avatar = user?['avatar_url'] as String? ?? '';
    final displayName = '${firstName.isNotEmpty ? firstName : ""} ${lastName.isNotEmpty ? lastName : ""}'.trim();

    return Scaffold(
      backgroundColor: AlluoraColors.cream,
      appBar: AppBar(
        title: const Text('You'),
        backgroundColor: AlluoraColors.cream,
        elevation: 0,
      ),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          // Header card
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: AlluoraColors.border),
            ),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 32,
                  backgroundColor: AlluoraColors.primaryLight,
                  child: avatar.isNotEmpty
                      ? ClipOval(child: CachedNetworkImage(imageUrl: avatar, width: 64, height: 64, fit: BoxFit.cover))
                      : Text(
                          (displayName.isNotEmpty ? displayName : email)[0].toUpperCase(),
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 22),
                        ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        displayName.isNotEmpty ? displayName : 'Alluora member',
                        style: AlluoraTypography.h3,
                      ),
                      const SizedBox(height: 4),
                      Text(email, style: AlluoraTypography.bodySmall.copyWith(color: AlluoraColors.textMuted)),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 24),

          _MenuItem(icon: Icons.person_outline, label: 'Edit profile', onTap: () {}),
          _MenuItem(icon: Icons.local_shipping_outlined, label: 'Addresses', onTap: () {}),
          _MenuItem(icon: Icons.receipt_long_outlined, label: 'Order history', onTap: () {}),
          _MenuItem(icon: Icons.quiz_outlined, label: 'Skin quiz', onTap: () {}),
          _MenuItem(icon: Icons.lock_outline, label: 'Change password', onTap: () {}),
          _MenuItem(icon: Icons.privacy_tip_outlined, label: 'Privacy policy', onTap: () {}),

          const SizedBox(height: 32),
          OutlinedButton.icon(
            onPressed: () async {
              final ok = await showDialog<bool>(
                context: context,
                builder: (_) => AlertDialog(
                  title: const Text('Sign out?'),
                  content: const Text("You'll be asked to sign in again next time."),
                  actions: [
                    TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
                    TextButton(onPressed: () => Navigator.pop(context, true), child: const Text('Sign out')),
                  ],
                ),
              );
              if (ok == true && context.mounted) {
                await AuthService.instance.logout();
              }
            },
            icon: const Icon(Icons.logout),
            label: const Text('Sign out'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(double.infinity, 52),
              side: const BorderSide(color: AlluoraColors.border),
              foregroundColor: AlluoraColors.textSecondary,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
            ),
          ),
        ],
      ),
    );
  }
}

class _MenuItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  const _MenuItem({required this.icon, required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 14),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: AlluoraColors.divider)),
        ),
        child: Row(
          children: [
            Icon(icon, color: AlluoraColors.textSecondary, size: 22),
            const SizedBox(width: 14),
            Expanded(child: Text(label, style: AlluoraTypography.bodyDefault)),
            const Icon(Icons.chevron_right, color: AlluoraColors.textMuted),
          ],
        ),
      ),
    );
  }
}
