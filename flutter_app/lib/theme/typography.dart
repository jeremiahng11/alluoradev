import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'colors.dart';

class AlluoraTypography {
  AlluoraTypography._();

  // Display family — used for headings and the wordmark feel.
  // Cormorant Garamond and Inter both come from Google Fonts at runtime;
  // no bundled .ttf files needed.
  static TextStyle _display(double size, {FontWeight weight = FontWeight.w400, FontStyle style = FontStyle.normal, Color? color, double? height}) {
    return GoogleFonts.cormorantGaramond(
      fontSize: size,
      fontWeight: weight,
      fontStyle: style,
      color: color ?? AlluoraColors.textPrimary,
      height: height,
      letterSpacing: -0.2,
    );
  }

  static TextStyle _body(double size, {FontWeight weight = FontWeight.w400, Color? color, double? height}) {
    return GoogleFonts.inter(
      fontSize: size,
      fontWeight: weight,
      color: color ?? AlluoraColors.textPrimary,
      height: height ?? 1.5,
      letterSpacing: 0,
    );
  }

  // Display
  static TextStyle hero        = _display(40, weight: FontWeight.w400, height: 1.1);
  static TextStyle h1          = _display(32, weight: FontWeight.w500, height: 1.15);
  static TextStyle h2          = _display(26, weight: FontWeight.w500, height: 1.2);
  static TextStyle h3          = _display(20, weight: FontWeight.w500, height: 1.3);
  static TextStyle quote       = _display(18, style: FontStyle.italic, height: 1.4);

  // Body
  static TextStyle bodyLarge   = _body(17, weight: FontWeight.w400);
  static TextStyle bodyDefault = _body(15, weight: FontWeight.w400);
  static TextStyle bodySmall   = _body(13, weight: FontWeight.w400, color: AlluoraColors.textSecondary);

  // UI
  static TextStyle button      = _body(15, weight: FontWeight.w600);
  static TextStyle label       = _body(13, weight: FontWeight.w500);
  static TextStyle caption     = _body(12, weight: FontWeight.w400, color: AlluoraColors.textMuted);
  static TextStyle overline    = _body(11, weight: FontWeight.w600, color: AlluoraColors.textSecondary)
      .copyWith(letterSpacing: 1.2);

  static TextTheme textTheme = TextTheme(
    displayLarge:   hero,
    displayMedium:  h1,
    headlineLarge:  h1,
    headlineMedium: h2,
    headlineSmall:  h3,
    titleLarge:     h3,
    titleMedium:    _body(16, weight: FontWeight.w600),
    bodyLarge:      bodyLarge,
    bodyMedium:     bodyDefault,
    bodySmall:      bodySmall,
    labelLarge:     button,
    labelMedium:    label,
    labelSmall:     caption,
  );
}
