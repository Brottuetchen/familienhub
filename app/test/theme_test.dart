import 'package:familienhub/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AppTheme provides dark material 3 theme', () {
    final theme = AppTheme.dark;
    expect(theme.brightness, Brightness.dark);
    expect(theme.useMaterial3, isTrue);
    expect(theme.colorScheme.brightness, Brightness.dark);
  });
}
