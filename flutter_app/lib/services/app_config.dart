/// Compile-time configuration. Override with --dart-define on flutter run/build.
class AppConfig {
  AppConfig._();

  /// WordPress + alluora-app-bridge plugin base URL.
  /// Owns: auth, customer profile, products, orders.
  static const String wordpressBase = String.fromEnvironment(
    'WORDPRESS_BASE',
    defaultValue: 'https://staging.alluora.com',
  );

  /// Django backend base URL.
  /// Owns: content, videos (Bunny), rewards, quizzes.
  static const String djangoBase = String.fromEnvironment(
    'DJANGO_BASE',
    defaultValue: 'https://staging-api.alluora.com',
  );

  /// Where the in-app webview opens for the storefront.
  /// Same domain as wordpressBase => cookies are shared automatically.
  static String shopUrl({String path = '/shop'}) => '$wordpressBase$path';

  /// Whether to dump verbose API logs.
  static const bool verboseLogging = bool.fromEnvironment('VERBOSE', defaultValue: false);
}
