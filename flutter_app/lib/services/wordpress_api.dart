import 'dart:io';

import 'package:cookie_jar/cookie_jar.dart';
import 'package:dio/dio.dart';
import 'package:dio_cookie_manager/dio_cookie_manager.dart';
import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'app_config.dart';

/// Talks to the alluora-app-bridge plugin on WordPress.
///
/// Auth model: WordPress sets HTTP-only cookies on /auth/login. The cookie
/// jar persists them between launches. Protected calls add the X-WP-Nonce
/// header automatically.
class WordPressApi {
  WordPressApi._();
  static final WordPressApi instance = WordPressApi._();

  late final Dio _dio;
  late final PersistCookieJar cookieJar;
  String? _nonce;

  bool _initialized = false;

  Future<void> init() async {
    if (_initialized) return;

    final dir = await getApplicationDocumentsDirectory();
    cookieJar = PersistCookieJar(
      storage: FileStorage('${dir.path}/.cookies/wp/'),
      ignoreExpires: false,
    );

    _dio = Dio(BaseOptions(
      baseUrl: '${AppConfig.wordpressBase}/wp-json/alluora/v1',
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 30),
      contentType: 'application/json',
      headers: {'Accept': 'application/json'},
      validateStatus: (s) => s != null && s < 500,
    ));

    _dio.interceptors.add(CookieManager(cookieJar));
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_nonce != null && _nonce!.isNotEmpty) {
          options.headers['X-WP-Nonce'] = _nonce!;
        }
        if (kDebugMode && AppConfig.verboseLogging) {
          // ignore: avoid_print
          print('→ ${options.method} ${options.uri}');
        }
        handler.next(options);
      },
      onResponse: (response, handler) {
        // Server may include a refreshed nonce in /me responses.
        final data = response.data;
        if (data is Map && data['data'] is Map && data['data']['nonce'] is String) {
          _nonce = data['data']['nonce'] as String;
        }
        handler.next(response);
      },
    ));

    _initialized = true;
  }

  String? get nonce => _nonce;
  set nonce(String? v) => _nonce = v;

  // ──────────────────────────────────────────────────────────────────────
  // Auth
  // ──────────────────────────────────────────────────────────────────────

  /// Log in. Returns the user payload from the plugin.
  Future<Map<String, dynamic>> login({
    required String identifier,
    required String password,
    bool remember = true,
  }) async {
    final res = await _dio.post('/auth/login', data: {
      'username_or_email': identifier,
      'password': password,
      'remember': remember,
    });
    final body = _unwrap(res);
    _nonce = body['nonce'] as String?;
    return body['user'] as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> register({
    required String email,
    required String password,
    String? firstName,
    String? lastName,
    String? phone,
  }) async {
    final res = await _dio.post('/auth/register', data: {
      'email': email,
      'password': password,
      if (firstName != null) 'first_name': firstName,
      if (lastName != null) 'last_name': lastName,
      if (phone != null) 'phone': phone,
    });
    final body = _unwrap(res);
    _nonce = body['nonce'] as String?;
    return body['user'] as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> me() async {
    try {
      final res = await _dio.get('/auth/me');
      if (res.statusCode == 401) return null;
      final body = _unwrap(res);
      _nonce = body['nonce'] as String?;
      return body['user'] as Map<String, dynamic>?;
    } on DioException {
      return null;
    }
  }

  Future<void> forgotPassword(String email) async {
    await _dio.post('/auth/forgot-password', data: {'email': email});
  }

  Future<void> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    final res = await _dio.post('/auth/change-password', data: {
      'current_password': currentPassword,
      'new_password': newPassword,
    });
    final body = _unwrap(res);
    if (body['nonce'] != null) _nonce = body['nonce'] as String;
  }

  Future<void> logout() async {
    try {
      await _dio.post('/auth/logout');
    } catch (_) {}
    await cookieJar.deleteAll();
    _nonce = null;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Customer
  // ──────────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> getProfile() async {
    final res = await _dio.get('/customer/profile');
    return _unwrap(res) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateProfile(Map<String, dynamic> patch) async {
    final res = await _dio.patch('/customer/profile', data: patch);
    return _unwrap(res) as Map<String, dynamic>;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Orders
  // ──────────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> listOrders({int page = 1, int perPage = 10, String? status}) async {
    final res = await _dio.get('/orders', queryParameters: {
      'page': page,
      'per_page': perPage,
      if (status != null) 'status': status,
    });
    return _unwrap(res) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getOrder(int id) async {
    final res = await _dio.get('/orders/$id');
    return _unwrap(res) as Map<String, dynamic>;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Products
  // ──────────────────────────────────────────────────────────────────────

  Future<Map<String, dynamic>> listProducts({
    int page = 1,
    int perPage = 20,
    String? search,
    String? category,
    bool? onSale,
  }) async {
    final res = await _dio.get('/products', queryParameters: {
      'page': page,
      'per_page': perPage,
      if (search != null) 'search': search,
      if (category != null) 'category': category,
      if (onSale == true) 'on_sale': 1,
    });
    return _unwrap(res) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getProduct(int id) async {
    final res = await _dio.get('/products/$id');
    return _unwrap(res) as Map<String, dynamic>;
  }

  Future<List<dynamic>> listCategories() async {
    final res = await _dio.get('/products/categories');
    final body = _unwrap(res);
    return body as List<dynamic>;
  }

  // ──────────────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────────────

  /// Unwrap the plugin's `{ success: true, data: {...} }` envelope and throw
  /// on error responses.
  dynamic _unwrap(Response res) {
    final data = res.data;
    if (res.statusCode != null && res.statusCode! >= 400) {
      final msg = (data is Map && data['message'] is String)
          ? data['message'] as String
          : 'Request failed (${res.statusCode}).';
      throw ApiException(msg, statusCode: res.statusCode);
    }
    if (data is Map && data['success'] == true && data.containsKey('data')) {
      return data['data'];
    }
    return data;
  }

  /// Cookies for the WP domain — used to seed webview_cookie_manager.
  Future<List<Cookie>> cookiesForWebView() async {
    final uri = Uri.parse(AppConfig.wordpressBase);
    return cookieJar.loadForRequest(uri);
  }
}

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  ApiException(this.message, {this.statusCode});
  @override
  String toString() => message;
}
