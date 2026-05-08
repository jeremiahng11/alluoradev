import 'package:flutter/foundation.dart';

import 'wordpress_api.dart';

enum AuthState { unknown, anonymous, authenticated }

/// Holds the current user across the app.
///
/// On startup, calls /auth/me to see if cookies are still valid.
/// Anything UI-facing should listen to this — go_router's redirect uses it.
class AuthService extends ChangeNotifier {
  AuthService._();
  static final AuthService instance = AuthService._();

  AuthState _state = AuthState.unknown;
  Map<String, dynamic>? _user;

  AuthState get state => _state;
  Map<String, dynamic>? get user => _user;
  bool get isAuthenticated => _state == AuthState.authenticated;

  Future<void> bootstrap() async {
    final me = await WordPressApi.instance.me();
    if (me != null) {
      _user = me;
      _state = AuthState.authenticated;
    } else {
      _user = null;
      _state = AuthState.anonymous;
    }
    notifyListeners();
  }

  Future<void> login({required String identifier, required String password}) async {
    final user = await WordPressApi.instance.login(
      identifier: identifier,
      password: password,
      remember: true,
    );
    _user = user;
    _state = AuthState.authenticated;
    notifyListeners();
  }

  Future<void> register({
    required String email,
    required String password,
    String? firstName,
    String? lastName,
    String? phone,
  }) async {
    final user = await WordPressApi.instance.register(
      email: email,
      password: password,
      firstName: firstName,
      lastName: lastName,
      phone: phone,
    );
    _user = user;
    _state = AuthState.authenticated;
    notifyListeners();
  }

  Future<void> logout() async {
    await WordPressApi.instance.logout();
    _user = null;
    _state = AuthState.anonymous;
    notifyListeners();
  }

  /// Refresh user info — call after profile updates, etc.
  Future<void> refresh() async {
    final me = await WordPressApi.instance.me();
    if (me != null) {
      _user = me;
      _state = AuthState.authenticated;
      notifyListeners();
    } else {
      // Cookie expired or rejected — drop to anonymous.
      _user = null;
      _state = AuthState.anonymous;
      notifyListeners();
    }
  }
}
