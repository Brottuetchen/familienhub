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
  });

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
  const TimetableData({
    required this.child,
    required this.entries,
    required this.settings,
    this.currentWeek,
    this.holidays = const [],
    this.canEdit = false,
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

  /// "School until 13:15, Swimming 16:00": lessons are merged into one part, everything else keeps its start.
  String get summary {
    final lessons = entries.where((e) => e.kind == 'school').toList();
    final parts = [
      if (holiday != null) l10n.timetableHolidays,
      if (lessons.isNotEmpty) l10n.timetableSchoolUntil(lessons.map((e) => e.end).reduce((a, b) => a.compareTo(b) >= 0 ? a : b)),
      for (final e in entries.where((e) => e.kind != 'school')) '${e.title} ${e.start}',
    ];
    return parts.join(', ');
  }
}

List<TodayTimetableChild> parseTodayTimetable(Object? json) {
  final children = json is Map ? json['children'] : null;
  return [
    for (final c in (children as List? ?? const []).whereType<Map<String, dynamic>>())
      TodayTimetableChild.fromJson(c),
  ];
}
