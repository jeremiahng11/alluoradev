import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:path_provider/path_provider.dart';

import 'app_config.dart';
import 'wordpress_api.dart';

/// Talks to the Django backend.
///
/// Authentication: Django's WordPressCookieAuthentication forwards the WP
/// cookie + X-WP-Nonce to /wp-json/alluora/v1/auth/me to identify the user.
/// So this client must:
///   1. Use a cookie jar that contains the WordPress cookies, AND
///   2. Send X-WP-Nonce on every request.
///
/// We achieve this by sharing the WordPressApi cookie jar's WP-domain cookies
/// for outgoing requests.
class DjangoApi {
  DjangoApi._();
  static final DjangoApi instance = DjangoApi._();

  late final Dio _dio;
  late final PersistCookieJar _cookieJar;
  bool _initialized = false;

  Future<void> init() async {
    if (_initialized) return;

    final dir = await getApplicationDocumentsDirectory();
    _cookieJar = PersistCookieJar(
      storage: FileStorage('${dir.path}/.cookies/django/'),
    );

    _dio = Dio(BaseOptions(
      baseUrl: '${AppConfig.djangoBase}/api/v1',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      contentType: 'application/json',
      headers: {'Accept': 'application/json'},
      validateStatus: (s) => s != null && s < 500,
    ));

    _dio.interceptors.add(CookieManager(_cookieJar));

    // Critical: Django's WP auth bridge expects the WP cookie + nonce.
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final wp = WordPressApi.instance;
        final wpCookies = await wp.cookiesForWebView();
        if (wpCookies.isNotEmpty) {
          // Build a Cookie header from WP cookies and append.
          final cookieHeader = wpCookies.map((c) => '${c.name}=${c.value}').join('; ');
          final existing = options.headers['Cookie'] as String?;
          options.headers['Cookie'] = existing == null || existing.isEmpty
              ? cookieHeader
              : '$existing; $cookieHeader';
        }
        if (wp.nonce != null && wp.nonce!.isNotEmpty) {
          options.headers['X-WP-Nonce'] = wp.nonce!;
        }
        handler.next(options);
      },
    ));

    _initialized = true;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Accounts
  // ──────────────────────────────────────────────────────────────────────

  /// GET /accounts/me/ — Django-side mirrored user record + reward points.
  Future<Map<String, dynamic>?> me() async {
    final res = await _dio.get('/accounts/me/');
    if (res.statusCode == 401 || res.statusCode == 403) return null;
    if (res.data is Map<String, dynamic>) return res.data as Map<String, dynamic>;
    return null;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Content
  // ──────────────────────────────────────────────────────────────────────

  Future<List<dynamic>> listArticles({bool? featured, String? search, int page = 1}) async {
    final res = await _dio.get('/content/articles/', queryParameters: {
      'page': page,
      if (featured != null) 'is_featured': featured,
      if (search != null && search.isNotEmpty) 'search': search,
    });
    final data = res.data;
    if (data is Map && data['results'] is List) return data['results'] as List;
    return [];
  }

  Future<Map<String, dynamic>?> getArticle(String slug) async {
    final res = await _dio.get('/content/articles/$slug/');
    if (res.data is Map<String, dynamic>) return res.data as Map<String, dynamic>;
    return null;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Videos
  // ──────────────────────────────────────────────────────────────────────

  Future<List<dynamic>> listVideos({int? collection, bool? featured}) async {
    final res = await _dio.get('/videos/', queryParameters: {
      if (collection != null) 'collection': collection,
      if (featured != null) 'is_featured': featured,
    });
    final data = res.data;
    if (data is Map && data['results'] is List) return data['results'] as List;
    return [];
  }

  // ──────────────────────────────────────────────────────────────────────
  // Rewards
  // ──────────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> rewardsBalance() async {
    final res = await _dio.get('/rewards/balance/');
    if (res.data is Map<String, dynamic>) return res.data as Map<String, dynamic>;
    return {'balance': 0, 'badges': []};
  }

  Future<List<dynamic>> rewardsHistory({int page = 1}) async {
    final res = await _dio.get('/rewards/history/', queryParameters: {'page': page});
    final data = res.data;
    if (data is Map && data['results'] is List) return data['results'] as List;
    return [];
  }

  // ──────────────────────────────────────────────────────────────────────
  // Quiz
  // ──────────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>?> getQuiz(String slug) async {
    final res = await _dio.get('/quiz/$slug/');
    if (res.data is Map<String, dynamic>) return res.data as Map<String, dynamic>;
    return null;
  }

  Future<Map<String, dynamic>> submitQuiz(String slug, List<int> optionIds) async {
    final res = await _dio.post('/quiz/$slug/submit/', data: {'answers': optionIds});
    return res.data as Map<String, dynamic>;
  }

  Future<List<dynamic>> mySubmissions() async {
    final res = await _dio.get('/quiz/submissions/');
    final data = res.data;
    if (data is Map && data['results'] is List) return data['results'] as List;
    return [];
  }
}
