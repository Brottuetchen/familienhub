import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:intl/intl.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'gen/app_localizations.dart';

export 'gen/app_localizations.dart';

/// Supported app languages (code -> own name), derived from the generated locales.
/// A new language only needs an `app_<code>.arb` with a translated `languageName`.
Map<String, String> get appLanguages => {
  for (final locale in AppLocalizations.supportedLocales)
    locale.languageCode: lookupAppLocalizations(locale).languageName,
};

const languagePrefKey = 'app_language';

AppLocalizations _current = lookupAppLocalizations(const Locale('de'));

/// Texte der aktuellen Sprache, auch außerhalb von Widgets (Dienste, Hintergrund, Mitteilungen).
AppLocalizations get l10n => _current;

/// Sprachcode der Oberfläche (`de`, `en`), z. B. für `Accept-Language`.
String get appLanguage => _current.localeName;

/// Gespeicherte Wahl (`system`, `de`, `en`) in einen Sprachcode übersetzen.
/// „system“: Deutsch, wenn das Gerät Deutsch spricht, sonst Englisch.
String resolveLanguage(String? choice, {Locale? device}) {
  if (choice != null && appLanguages.containsKey(choice)) return choice;
  final code = (device ?? PlatformDispatcher.instance.locale).languageCode;
  return appLanguages.containsKey(code) ? code : 'en';
}

/// Sprache setzen: Texte, Datums- und Zahlenformate.
void setAppLanguage(String code) {
  _current = lookupAppLocalizations(Locale(code));
  Intl.defaultLocale = code == 'de' ? 'de_DE' : 'en_US';
}

/// Für Hintergrund-Isolates und den Start: gespeicherte Wahl laden und setzen.
Future<String> loadAppLanguage() async {
  String? choice;
  try {
    choice = (await SharedPreferences.getInstance()).getString(languagePrefKey);
  } catch (_) {}
  final code = resolveLanguage(choice);
  setAppLanguage(code);
  return code;
}

/// Englische Entsprechung der (deutschen) Datumsmuster im Code. Unbekannte Muster bleiben gleich.
const _enPatterns = {
  'd.M. HH:mm:ss': 'M/d HH:mm:ss',
  'd.M. HH:mm': 'M/d HH:mm',
  'dd.MM. HH:mm': 'MM/dd HH:mm',
  'EEEE, d. MMMM': 'EEEE, MMMM d',
  'EEE, d. MMM': 'EEE, MMM d',
  'EEE, d. MMMM y': 'EEE, MMMM d, y',
  'd.M.yyyy': 'M/d/yyyy',
  'd.M.yyyy HH:mm': 'M/d/yyyy HH:mm',
  'd.M.': 'M/d',
  'E, d.M.': 'E, M/d',
  'EEE d.M., HH:mm': 'EEE M/d, HH:mm',
  'EEE, d.M. HH:mm': 'EEE, M/d HH:mm',
  'd.': 'd',
  'd. MMMM': 'MMMM d',
};

/// Datumsformat in der Sprache der App. Muster werden deutsch notiert, Englisch über [_enPatterns].
DateFormat localDate(String dePattern) =>
    appLanguage == 'de' ? DateFormat(dePattern, 'de_DE') : DateFormat(_enPatterns[dePattern] ?? dePattern, 'en_US');
