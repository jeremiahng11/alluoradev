import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../screens/auth/login_screen.dart';
import '../screens/auth/register_screen.dart';
import '../screens/auth/forgot_password_screen.dart';
import '../screens/onboarding/onboarding_screen.dart';
import '../screens/splash/splash_screen.dart';
import '../screens/home/home_screen.dart';
import '../screens/home/main_shell.dart';
import '../screens/shop/shop_screen.dart';
import '../screens/orders/card_screen.dart';
import '../screens/profile/profile_screen.dart';
import '../screens/content/article_detail_screen.dart';
import '../services/auth_service.dart';

class AppRouter {
  AppRouter._();

  static GoRouter create(AuthService auth) {
    return GoRouter(
      initialLocation: '/splash',
      refreshListenable: auth,
      redirect: (context, state) {
        final loc = state.matchedLocation;
        final isAuthRoute = loc == '/login' ||
            loc == '/register' ||
            loc == '/forgot-password' ||
            loc == '/onboarding';
        final isSplash = loc == '/splash';

        // While auth is unknown, stay on splash.
        if (auth.state == AuthState.unknown) {
          return isSplash ? null : '/splash';
        }

        // Anonymous users go to onboarding/login.
        if (auth.state == AuthState.anonymous) {
          return isAuthRoute ? null : '/onboarding';
        }

        // Authenticated users skip auth routes.
        if (auth.state == AuthState.authenticated) {
          if (isSplash || isAuthRoute) return '/home';
          return null;
        }

        return null;
      },
      routes: [
        GoRoute(path: '/splash', builder: (c, s) => const SplashScreen()),
        GoRoute(path: '/onboarding', builder: (c, s) => const OnboardingScreen()),
        GoRoute(path: '/login', builder: (c, s) => const LoginScreen()),
        GoRoute(path: '/register', builder: (c, s) => const RegisterScreen()),
        GoRoute(path: '/forgot-password', builder: (c, s) => const ForgotPasswordScreen()),

        // Article detail outside the shell so it's full-screen.
        GoRoute(
          path: '/articles/:slug',
          builder: (c, s) => ArticleDetailScreen(slug: s.pathParameters['slug']!),
        ),

        // Authenticated bottom-nav shell.
        ShellRoute(
          builder: (context, state, child) => MainShell(child: child),
          routes: [
            GoRoute(path: '/home', builder: (c, s) => const HomeScreen()),
            GoRoute(path: '/card', builder: (c, s) => const CardScreen()),
            GoRoute(path: '/shop', builder: (c, s) => const ShopScreen()),
            GoRoute(path: '/profile', builder: (c, s) => const ProfileScreen()),
          ],
        ),
      ],
      errorBuilder: (context, state) => Scaffold(
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.error_outline, size: 48),
                const SizedBox(height: 12),
                Text('Page not found', style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(state.matchedLocation, style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () => context.go('/home'),
                  child: const Text('Go home'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
