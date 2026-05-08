import 'package:flutter/material.dart';
import 'package:webview_cookie_manager/webview_cookie_manager.dart' as wcm;
import 'package:webview_flutter/webview_flutter.dart';

import '../../services/app_config.dart';
import '../../services/wordpress_api.dart';
import '../../theme/colors.dart';

/// Embeds the Alluora storefront. Cookies from the WordPress login are
/// synced into the webview, so the user lands on /shop already logged in.
class ShopScreen extends StatefulWidget {
  const ShopScreen({super.key});

  @override
  State<ShopScreen> createState() => _ShopScreenState();
}

class _ShopScreenState extends State<ShopScreen> {
  late final WebViewController _controller;
  bool _ready = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(AlluoraColors.cream)
      ..setNavigationDelegate(NavigationDelegate(
        onProgress: (_) {},
        onPageStarted: (_) {},
        onPageFinished: (_) {},
        onWebResourceError: (_) {},
      ));
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    // Pull cookies from the dio cookie jar and inject into the webview.
    final cookies = await WordPressApi.instance.cookiesForWebView();
    final manager = wcm.WebviewCookieManager();
    final host = Uri.parse(AppConfig.wordpressBase).host;

    for (final c in cookies) {
      await manager.setCookies([
        wcm.Cookie(c.name, c.value)
          ..domain = c.domain ?? host
          ..path = '/'
          ..secure = c.secure
          ..httpOnly = c.httpOnly,
      ]);
    }

    await _controller.loadRequest(Uri.parse(AppConfig.shopUrl(path: '/shop')));
    if (!mounted) return;
    setState(() => _ready = true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AlluoraColors.cream,
      body: SafeArea(
        child: _ready
            ? WebViewWidget(controller: _controller)
            : const Center(
                child: CircularProgressIndicator(color: AlluoraColors.primary),
              ),
      ),
    );
  }
}
