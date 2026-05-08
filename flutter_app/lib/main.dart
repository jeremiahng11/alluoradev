import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'router/app_router.dart';
import 'services/auth_service.dart';
import 'services/django_api.dart';
import 'services/wordpress_api.dart';
import 'theme/theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Set the system UI overlay to match the cream background.
  SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: Brightness.dark,
  ));

  // Init API clients (cookie jars need to load).
  await WordPressApi.instance.init();
  await DjangoApi.instance.init();

  // Bootstrap auth state from persisted cookies.
  await AuthService.instance.bootstrap();

  runApp(const AlluoraApp());
}

class AlluoraApp extends StatelessWidget {
  const AlluoraApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ChangeNotifierProvider<AuthService>.value(
      value: AuthService.instance,
      child: Consumer<AuthService>(
        builder: (context, auth, _) {
          final router = AppRouter.create(auth);
          return MaterialApp.router(
            title: 'Alluora',
            theme: AlluoraTheme.light,
            debugShowCheckedModeBanner: false,
            routerConfig: router,
          );
        },
      ),
    );
  }
}
