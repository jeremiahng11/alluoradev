import 'package:flutter/material.dart';

/// Alluora brand palette. Sourced from the latest mockup + the logo PNG.
class AlluoraColors {
  AlluoraColors._();

  // Primary — the iconic orange/terracotta from the logo.
  static const Color primary = Color(0xFFDD5430);
  static const Color primaryDark = Color(0xFFC44525);
  static const Color primaryLight = Color(0xFFE0976F);

  // Cream backgrounds (Begin page, content surfaces).
  static const Color cream = Color(0xFFFAF3E8);
  static const Color creamSoft = Color(0xFFFAF7F1);

  // Ink (used for the serif "a" inside the disc on the logo, and for body text).
  static const Color ink = Color(0xFF1A1410);
  static const Color textPrimary = Color(0xFF1F1A14);
  static const Color textSecondary = Color(0xFF6B6157);
  static const Color textMuted = Color(0xFF9C9389);

  // Surfaces & borders.
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceAlt = Color(0xFFF5F0E6);
  static const Color surfaceWarm = Color(0xFFFBF1E0);
  static const Color border = Color(0xFFE5DDD0);
  static const Color divider = Color(0xFFEEE7DB);

  // Status.
  static const Color success = Color(0xFF4A7C2E);
  static const Color error = Color(0xFFB8341F);
  static const Color warning = Color(0xFFC58B2A);
}
