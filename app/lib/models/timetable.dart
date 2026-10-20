import '../l10n/l10n.dart';

/// Kinds of timetable entries, in the order the editor offers them.
const timetableKinds = ['school', 'sport', 'music', 'club', 'other'];

/// Week variants: every week, or only the A / B weeks.
const timetableWeeks = ['all', 'a', 'b'];

class TimetableEntry {
  final int id;
  final int childId;
  final int weekday; // 0 = Monday
  final String week; // all | a | b
  final String start; // HH:MM
  final String end;
  final String title;
  final String kind;
  final String? location;

  /// Only for lessons of a plugin (and entries merged into a dated day): the date, the state of the lesson
  /// (`normal`, `cancelled`, `substitution`, `changed`), a note, the teacher and the period number.
  final DateTime? date;
  final String status;
  final String? note;
  final String? teacher;
  final int? period;
  const TimetableEntry({
    required this.id,
    required this.childId,
    required this.weekday,
    required this.week,
    required this.start,
    required this.end,
    required this.title,
    required this.kind,
    this.location,
    this.date,
    this.status = 'normal',
    this.note,
    this.teacher,
    this.period,
  });

  bool get isCancelled => status == 'cancelled';

  /// A substituted or otherwise changed lesson (highlighted).
  bool get isChanged => status == 'substitution' || status == 'changed';

  factory TimetableEntry.fromJson(Map<String, dynamic> json) => TimetableEntry(
        id: (json['id'] as num?)?.toInt() ?? 0,
        childId: (json['child_id'] as num?)?.toInt() ?? 0,
        weekday: (json['weekday'] as num?)?.toInt() ?? 0,
        week: json['week'] as String? ?? 'all',
        start: json['start'] as String? ?? '',
        end: json['end'] as String? ?? '',
        title: json['title'] as String? ?? '',
        kind: json['kind'] as String? ?? 'other',
        location: json['location'] as String?,
        date: json['date'] == null ? null : DateTime.tryParse('${json['date']}'),
        status: json['status'] as String? ?? 'normal',
        note: json['note'] as String?,
        teacher: json['teacher'] as String?,
        period: (json['period'] as num?)?.toInt(),
      );
}

class HolidayPeriod {
  final DateTime start;
  final DateTime end; // inclusive
  final String title;
  const HolidayPeriod(this.start, this.end, this.title);

  static HolidayPeriod? tryParse(Object? json) {
    if (json is! Map) return null;
    final s = DateTime.tryParse('${json['start']}');
    final e = DateTime.tryParse('${json['end']}');
    if (s == null || e == null) return null;
    return HolidayPeriod(s, e, '${json['title'] ?? ''}');
  }
}

class TimetableFeed {
  final String id;
  final String name;
  const TimetableFeed(this.id, this.name);
}

class TimetableSettings {
  final DateTime? abReference;
  final String? holidayFeed;
  final List<TimetableFeed> feeds;
  const TimetableSettings({this.abReference, this.holidayFeed, this.feeds = const []});

  factory TimetableSettings.fromJson(Map<String, dynamic> json) => TimetableSettings(
        abReference: json['ab_reference'] == null ? null : DateTime.tryParse('${json['ab_reference']}'),
        holidayFeed: json['holiday_feed'] as String?,
        feeds: [
          for (final f in (json['feeds'] as List? ?? const []).whereType<Map>())
            TimetableFeed('${f['id']}', '${f['name']}'),
        ],
      );

  bool get hasAbWeeks => abReference != null;
}

class TimetableChild {
  final int id;
  final String name;
  const TimetableChild(this.id, this.name);

  static List<TimetableChild> list(Object? json) => [
        for (final c in (json as List? ?? const []).whereType<Map>())
          TimetableChild((c['id'] as num).toInt(), '${c['name']}'),
      ];
}

class TimetableData {
  final TimetableChild child;
  final List<TimetableEntry> entries;
  final TimetableSettings settings;
  final String? currentWeek; // 'a' | 'b' | null without A/B weeks
  final List<HolidayPeriod> holidays;
  final bool canEdit;

  /// The plugin that provides this child's lessons, if a parent mapped one.
  final TimetablePluginInfo? plugin;
  const TimetableData({
    required this.child,
    required this.entries,
    required this.settings,
    this.currentWeek,
    this.holidays = const [],
    this.canEdit = false,
    this.plugin,
  });

  factory TimetableData.fromJson(Map<String, dynamic> json) {
    final child = json['child'] as Map<String, dynamic>;
    return TimetableData(
      child: TimetableChild((child['id'] as num).toInt(), '${child['name']}'),
      entries: [
        for (final e in (json['entries'] as List? ?? const []).whereType<Map<String, dynamic>>())
          TimetableEntry.fromJson(e),
      ],
      settings: TimetableSettings.fromJson((json['settings'] as Map?)?.cast<String, dynamic>() ?? const {}),
      currentWeek: json['current_week'] as String?,
      holidays: (json['holidays'] as List? ?? const []).map(HolidayPeriod.tryParse).whereType<HolidayPeriod>().toList(),
      canEdit: json['can_edit'] == true,
      plugin: TimetablePluginInfo.tryParse(json['plugin']),
    );
  }

  /// Entries of one day for the shown week variant: the ones for every week plus the chosen A/B week.
  List<TimetableEntry> forDay(int weekday, String week) => [
        for (final e in entries)
          if (e.weekday == weekday && (e.week == 'all' || e.week == week || week == 'all')) e,
      ];
}

/// One child on the Today card.
class TodayTimetableChild {
  final int childId;
  final String name;
  final String? holiday;
  final List<TimetableEntry> entries;
  const TodayTimetableChild({required this.childId, required this.name, this.holiday, this.entries = const []});

  factory TodayTimetableChild.fromJson(Map<String, dynamic> json) => TodayTimetableChild(
        childId: (json['child_id'] as num?)?.toInt() ?? 0,
        name: json['name'] as String? ?? '',
        holiday: json['holiday'] as String?,
        entries: [
          for (final e in (json['entries'] as List? ?? const []).whereType<Map<String, dynamic>>())
            TimetableEntry.fromJson(e),
        ],
      );

  /// "School until 13:15, 1st–2nd period cancelled, Swimming 16:00": lessons are merged into one part, everything
  /// else keeps its start. Cancelled lessons do not count for "until"; substitutions are counted.
  String get summary {
    final school = entries.where((e) => e.kind == 'school').toList();
    final active = school.where((e) => !e.isCancelled).toList();
    final cancelled = school.where((e) => e.isCancelled).toList();
    final changed = school.where((e) => e.isChanged).length;
    final periods = [for (final e in cancelled) e.period];
    final parts = [
      if (holiday != null) l10n.timetableHolidays,
      if (active.isNotEmpty) l10n.timetableSchoolUntil(active.map((e) => e.end).reduce((a, b) => a.compareTo(b) >= 0 ? a : b)),
      if (active.isEmpty && cancelled.isNotEmpty)
        l10n.timetableSchoolCancelled
      else if (cancelled.isNotEmpty)
        periods.every((p) => p != null)
            ? l10n.timetablePeriodsCancelled(periodRanges(periods.cast<int>()))
            : l10n.timetableLessonsCancelled(cancelled.length),
      if (changed > 0) l10n.timetableSubstitutions(changed),
      for (final e in entries.where((e) => e.kind != 'school'))
        e.isCancelled ? l10n.timetableEntryCancelled(e.title) : '${e.title} ${e.start}',
    ];
    return parts.join(', ');
  }
}

/// "1st", "2nd" (English) or "1." (German).
String periodOrdinal(int n) {
  if (appLanguage == 'de') return '$n.';
  final tens = n % 100;
  if (tens >= 11 && tens <= 13) return '${n}th';
  return switch (n % 10) { 1 => '${n}st', 2 => '${n}nd', 3 => '${n}rd', _ => '${n}th' };
}

/// Period numbers as ranges: [1, 2, 4] -> "1st–2nd, 4th".
String periodRanges(List<int> periods) {
  final sorted = {...periods}.toList()..sort();
  final out = <String>[];
  var i = 0;
  while (i < sorted.length) {
    var j = i;
    while (j + 1 < sorted.length && sorted[j + 1] == sorted[j] + 1) {
      j++;
    }
    out.add(j > i ? '${periodOrdinal(sorted[i])}–${periodOrdinal(sorted[j])}' : periodOrdinal(sorted[i]));
    i = j + 1;
  }
  return out.join(', ');
}

/// Which plugin provides a child's lessons (`status`: `ok`, `unavailable`).
class TimetablePluginInfo {
  final String id;
  final String name;
  final String? person;
  final String status;
  const TimetablePluginInfo({required this.id, required this.name, this.person, this.status = 'ok'});

  bool get unavailable => status == 'unavailable';

  static TimetablePluginInfo? tryParse(Object? json) {
    if (json is! Map) return null;
    return TimetablePluginInfo(
      id: '${json['id']}',
      name: '${json['name'] ?? json['id']}',
      person: json['person'] as String?,
      status: json['status'] as String? ?? 'ok',
    );
  }
}

/// One real day of the week view: manual entries merged with the plugin's lessons.
class TimetableDay {
  final DateTime date;
  final int weekday;
  final String source; // plugin | manual
  final String? holiday;
  final List<TimetableEntry> entries;
  const TimetableDay({required this.date, required this.weekday, required this.source, this.holiday, this.entries = const []});

  factory TimetableDay.fromJson(Map<String, dynamic> json) => TimetableDay(
        date: DateTime.parse('${json['date']}'),
        weekday: (json['weekday'] as num?)?.toInt() ?? 0,
        source: json['source'] as String? ?? 'manual',
        holiday: json['holiday'] as String?,
        entries: [
          for (final e in (json['entries'] as List? ?? const []).whereType<Map<String, dynamic>>())
            TimetableEntry.fromJson(e),
        ],
      );
}

/// `/api/timetable/week`: a calendar week of a child with real dates.
class TimetableWeek {
  final TimetableChild child;
  final DateTime start;
  final String? week; // a | b | null
  final TimetablePluginInfo? plugin;
  final List<TimetableDay> days;
  const TimetableWeek({required this.child, required this.start, this.week, this.plugin, this.days = const []});

  factory TimetableWeek.fromJson(Map<String, dynamic> json) {
    final child = json['child'] as Map<String, dynamic>;
    return TimetableWeek(
      child: TimetableChild((child['id'] as num).toInt(), '${child['name']}'),
      start: DateTime.parse('${json['start']}'),
      week: json['week'] as String?,
      plugin: TimetablePluginInfo.tryParse(json['plugin']),
      days: [
        for (final d in (json['days'] as List? ?? const []).whereType<Map<String, dynamic>>()) TimetableDay.fromJson(d),
      ],
    );
  }
}

/// A person in the plugin's system a child can be mapped to.
class TimetablePerson {
  final String id;
  final String name;
  const TimetablePerson(this.id, this.name);
}

/// A plugin that can provide timetables; [peopleKnown]: it lists its people (dropdown), else a free identifier.
class TimetablePluginRef {
  final String id;
  final String name;
  final List<TimetablePerson> people;
  final bool peopleKnown;
  const TimetablePluginRef({required this.id, required this.name, this.people = const [], this.peopleKnown = false});
}

class TimetableChildSource {
  final int childId;
  final String name;
  final String? pluginId;
  final String? personId;
  const TimetableChildSource({required this.childId, required this.name, this.pluginId, this.personId});
}

/// `/api/timetable/sources`: the mapping of children to plugin people, and the plugins that can provide timetables.
class TimetableSources {
  final List<TimetableChildSource> children;
  final List<TimetablePluginRef> plugins;
  const TimetableSources({this.children = const [], this.plugins = const []});

  factory TimetableSources.fromJson(Map<String, dynamic> json) => TimetableSources(
        children: [
          for (final c in (json['children'] as List? ?? const []).whereType<Map>())
            TimetableChildSource(
              childId: (c['child_id'] as num).toInt(),
              name: '${c['name']}',
              pluginId: c['plugin_id'] as String?,
              personId: c['person_id'] as String?,
            ),
        ],
        plugins: [
          for (final p in (json['plugins'] as List? ?? const []).whereType<Map>())
            TimetablePluginRef(
              id: '${p['id']}',
              name: '${p['name']}',
              peopleKnown: p['people_known'] == true,
              people: [
                for (final x in (p['people'] as List? ?? const []).whereType<Map>()) TimetablePerson('${x['id']}', '${x['name']}'),
              ],
            ),
        ],
      );
}

List<TodayTimetableChild> parseTodayTimetable(Object? json) {
  final children = json is Map ? json['children'] : null;
  return [
    for (final c in (children as List? ?? const []).whereType<Map<String, dynamic>>())
      TodayTimetableChild.fromJson(c),
  ];
}
