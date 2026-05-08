import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../theme/colors.dart';

/// The Alluora wordmark + icon, rendered as Flutter widgets so we don't
/// depend on shipping the PNG (though we can switch to that easily).
///
/// Layout: orange disc with a serif italic "a" inside, dot accent at lower
/// right, "alluora" wordmark below in primary orange.
///
/// Compatibility note: an older version of this widget used `showWordmark`.
/// We accept `withWordmark` as well so callers using either name work.
class AlluoraLogo extends StatelessWidget {
  final double size;
  final bool showWordmark;
  final Color discColor;
  final Color wordmarkColor;
  final Color letterColor;

  const AlluoraLogo({
    super.key,
    this.size = 120,
    bool? showWordmark,
    bool? withWordmark,
    this.discColor = AlluoraColors.primary,
    this.wordmarkColor = AlluoraColors.primary,
    this.letterColor = AlluoraColors.ink,
  }) : showWordmark = showWordmark ?? withWordmark ?? true;

  @override
  Widget build(BuildContext context) {
    final discSize = size;
    final wordmarkSize = size * 0.42;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(
          width: discSize,
          height: discSize,
          child: Stack(
            alignment: Alignment.center,
            children: [
              // Disc
              Container(
                width: discSize * 0.78,
                height: discSize * 0.78,
                decoration: BoxDecoration(
                  color: discColor,
                  shape: BoxShape.circle,
                ),
              ),
              // Italic serif 'a' centered on the disc.
              Padding(
                padding: EdgeInsets.only(top: discSize * 0.05),
                child: Text(
                  'a',
                  style: GoogleFonts.cormorantGaramond(
                    fontSize: discSize * 0.62,
                    fontWeight: FontWeight.w500,
                    fontStyle: FontStyle.italic,
                    color: letterColor,
                    height: 1,
                  ),
                ),
              ),
              // Dot accent at lower right of the disc.
              Positioned(
                right: discSize * 0.16,
                bottom: discSize * 0.18,
                child: Container(
                  width: discSize * 0.05,
                  height: discSize * 0.05,
                  decoration: BoxDecoration(
                    color: discColor,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            ],
          ),
        ),
        if (showWordmark) ...[
          SizedBox(height: size * 0.08),
          Text(
            'alluora',
            style: GoogleFonts.cormorantGaramond(
              fontSize: wordmarkSize,
              fontWeight: FontWeight.w300,
              color: wordmarkColor,
              letterSpacing: 0.5,
              height: 1,
            ),
          ),
        ],
      ],
    );
  }
}
