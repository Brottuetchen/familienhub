import 'common.dart';
import '../l10n/l10n.dart';

class CalendarEvent {
  /// Only events of the hub's family calendar have an id (and can be deleted in the app).
  final int? id;
  final String? source; // caldav | hub | ics …
  final String title;
  final DateTime? start;
  final DateTime? end;
  final bool allDay;
  final String? location;
  final String? calendar;
  final String? color;

  const CalendarEvent({
    this.id,
    this.source,
    required this.title,
    this.start,
    this.end,
    this.allDay = false,
    this.location,
    this.calendar,
    this.color,
  });

  /// Does the event take place on [day]? All-day ends are exclusive (ICS), timed events count on every touched day.
  bool occursOn(DateTime day) {
    final s = start;
    if (s == null) return false;
    final d = DateTime(day.year, day.month, day.day);
    final first = DateTime(s.year, s.month, s.day);
    final e = end;
    if (e == null) return d == first;
    if (allDay) {
      final last = DateTime(e.year, e.month, e.day);
      return !d.isBefore(first) && (d.isBefore(last) || (last == first && d == first));
    }
    final lastTouched = DateTime(e.year, e.month, e.day);
    final last = e.hour == 0 && e.minute == 0 && lastTouched.isAfter(first) ? lastTouched.subtract(const Duration(days: 1)) : lastTouched;
    return !d.isBefore(first) && !d.isAfter(last);
  }

  /// Spans more than one day (holidays, trips): shown as a bar in the month view.
  bool get isMultiDay {
    final s = start, e = end;
    if (s == null || e == null) return false;
    final days = DateTime(e.year, e.month, e.day).difference(DateTime(s.year, s.month, s.day)).inDays;
    return allDay ? days > 1 : days >= 1 && !(days == 1 && e.hour == 0 && e.minute == 0);
  }

  factory CalendarEvent.fromJson(Map<String, dynamic> json) {
    final allDay = json['all_day'] == true;
    DateTime? parse(Object? raw) => allDay ? parseDay(raw) : parseDate(raw);
    return CalendarEvent(
      id: json['id'] is int ? json['id'] as int : null,
      source: json['source'] as String?,
      title: (json['title'] as String?) ?? l10n.event,
      start: parse(json['start']),
      end: parse(json['end']),
      allDay: allDay,
      location: json['location'] as String?,
      calendar: json['calendar'] as String?,
      color: json['color'] as String?,
    );
  }
}
