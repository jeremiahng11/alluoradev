import 'package:flutter/material.dart';

import 'colors.dart';
import 'typography.dart';

class AlluoraTheme {
  AlluoraTheme._();

  static ThemeData light = ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    scaffoldBackgroundColor: AlluoraColors.cream,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AlluoraColors.primary,
      primary: AlluoraColors.primary,
      onPrimary: Colors.white,
      secondary: AlluoraColors.primaryLight,
      surface: AlluoraColors.surface,
      onSurface: AlluoraColors.textPrimary,
      error: AlluoraColors.error,
      brightness: Brightness.light,
    ),
    textTheme: AlluoraTypography.textTheme,

    appBarTheme: AppBarTheme(
      backgroundColor: AlluoraColors.cream,
      foregroundColor: AlluoraColors.textPrimary,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: AlluoraTypography.h3,
      iconTheme: const IconThemeData(color: AlluoraColors.textPrimary),
    ),

    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AlluoraColors.primary,
        foregroundColor: Colors.white,
        elevation: 0,
        textStyle: AlluoraTypography.button,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
        minimumSize: const Size(double.infinity, 52),
      ),
    ),

    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: AlluoraColors.primary,
        textStyle: AlluoraTypography.button,
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        side: const BorderSide(color: AlluoraColors.primary, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
        minimumSize: const Size(double.infinity, 52),
      ),
    ),

    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: AlluoraColors.primary,
        textStyle: AlluoraTypography.button,
      ),
    ),

    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white,
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AlluoraColors.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AlluoraColors.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AlluoraColors.primary, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: AlluoraColors.error),
      ),
      labelStyle: AlluoraTypography.label.copyWith(color: AlluoraColors.textSecondary),
      hintStyle: AlluoraTypography.bodyDefault.copyWith(color: AlluoraColors.textMuted),
    ),

    bottomNavigationBarTheme: const BottomNavigationBarThemeData(
      backgroundColor: Colors.white,
      selectedItemColor: AlluoraColors.primary,
      unselectedItemColor: AlluoraColors.textMuted,
      type: BottomNavigationBarType.fixed,
      showUnselectedLabels: true,
      elevation: 8,
    ),

    cardTheme: CardThemeData(
      color: Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: const BorderSide(color: AlluoraColors.border),
      ),
    ),

    dividerTheme: const DividerThemeData(
      color: AlluoraColors.divider,
      thickness: 1,
      space: 1,
    ),

    snackBarTheme: SnackBarThemeData(
      backgroundColor: AlluoraColors.ink,
      contentTextStyle: AlluoraTypography.bodyDefault.copyWith(color: Colors.white),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
    ),
  );
}
