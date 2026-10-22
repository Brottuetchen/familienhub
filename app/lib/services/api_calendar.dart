part of 'api_client.dart';

/// Calendar events and reminders.
mixin CalendarApi on ApiClientBase {
  // ── Termine ────────────────────────────────────────────────────────────────

  Future<List<CalendarInfo>> calendars() async =>
      _maps(await _send('GET', '/api/calendar/calendars')).map(CalendarInfo.fromJson).toList();

  /// Events of a range (month or week grid), also in the past.
  Future<ApiResult<List<CalendarEvent>>> eventsRange(DateTime start, int days) => _cachedGet(
      '/api/calendar/events?start=${_dateOnly(start)}&days=$days', 'events:${_dateOnly(start)}:$days',
      (j) => _maps(j).map(CalendarEvent.fromJson).toList());

  Future<ApiResult<List<CalendarEvent>>> events({int days = 14}) => _cachedGet(
      '/api/calendar/events?days=$days', 'events:$days', (j) => _maps(j).map(CalendarEvent.fromJson).toList());

  Future<void> createEvent({
    required String title,
    required DateTime start,
    required DateTime end,
    required bool allDay,
    String? calendarId,
    String? location,
    String? notes,
    String recurrence = 'none',
    int? alarmMinutes,
  }) =>
      _send('POST', '/api/calendar/events', body: {
        'title': title,
        'start': allDay ? _dateOnly(start) : _localIso(start),
        'end': allDay ? _dateOnly(end) : _localIso(end),
        'all_day': allDay,
        if (calendarId != null) 'calendar_id': calendarId,
        if (location != null && location.isNotEmpty) 'location': location,
        if (notes != null && notes.isNotEmpty) 'notes': notes,
        if (recurrence != 'none') 'recurrence': recurrence,
        'alarm_minutes': alarmMinutes,
      });

  // ── Erinnerungen ───────────────────────────────────────────────────────────

  Future<List<Reminder>> reminders() async =>
      _maps(await _send('GET', '/api/reminders')).map(Reminder.fromJson).toList();

  Future<void> createReminder(String title, DateTime? dueAt,
          {bool forFamily = false, String recurrence = 'none', bool onArrival = false}) =>
      _send('POST', '/api/reminders', body: {
        'title': title,
        if (dueAt != null && !onArrival) 'due_at': _localIso(dueAt),
        'for_family': forFamily,
        'recurrence': recurrence,
        'fire_on': onArrival ? 'arrival' : 'time',
      });

  Future<void> snoozeReminder(int id, int minutes) =>
      _send('POST', '/api/reminders/$id/snooze', body: {'minutes': minutes});

  Future<void> completeReminder(int id) =>
      _send('PATCH', '/api/reminders/$id', body: {'completed': true});

  Map<String, dynamic> _eventBody(String title, DateTime start, DateTime end, bool allDay, String? location, String? notes,
          String recurrence, int? alarmMinutes) =>
      {
        'title': title,
        'start': allDay ? _dateOnly(start) : _localIso(start),
        'end': allDay ? _dateOnly(end) : _localIso(end),
        'all_day': allDay,
        'location': location ?? '',
        'notes': notes ?? '',
        'recurrence': recurrence,
        'alarm_minutes': alarmMinutes,
      };

  /// Edits an event: hub family calendar by id, own CalDAV calendar by calendar id and uid.
  Future<void> updateEvent(CalendarEvent e, {required String title, required DateTime start, required DateTime end,
      required bool allDay, String? location, String? notes, String recurrence = 'none', int? alarmMinutes}) {
    final body = _eventBody(title, start, end, allDay, location, notes, recurrence, alarmMinutes);
    if (e.source == 'hub' && e.id != null) return _send('PUT', '/api/calendar/events/${e.id}', body: body);
    return _send('PUT', '/api/calendar/caldav/${e.calendarId!.replaceAll(RegExp(r'[^a-z0-9:-]'), '')}/${Uri.encodeComponent(e.uid!)}', body: body);
  }

  Future<void> deleteAnyEvent(CalendarEvent e) => e.source == 'hub' && e.id != null
      ? _send('DELETE', '/api/calendar/events/${e.id}')
      : _send('DELETE', '/api/calendar/caldav/${e.calendarId!.replaceAll(RegExp(r'[^a-z0-9:-]'), '')}/${Uri.encodeComponent(e.uid!)}');

  /// Own setting: calendar synced on the phone → the phone alerts, the hub sends no event reminders.
  Future<bool> calendarOnPhone() async =>
      ((await _send('GET', '/api/calendar/me/reminders')) as Map<String, dynamic>)['calendar_on_phone'] == true;

  Future<void> setCalendarOnPhone(bool value) =>
      _send('PUT', '/api/calendar/me/reminders', body: {'calendar_on_phone': value});

  /// Only events of the hub's family calendar can be deleted here.
  Future<void> deleteEvent(int id) => _send('DELETE', '/api/calendar/events/$id');

  /// Copies the event into [toCalendarId] and removes it from the source.
  Future<void> moveEvent({required String fromCalendarId, required String toCalendarId, int? eventId, String? uid}) =>
      _send('POST', '/api/calendar/move', body: {
        'from_calendar_id': fromCalendarId,
        'to_calendar_id': toCalendarId,
        if (eventId != null) 'event_id': eventId,
        if (uid != null) 'uid': uid,
      });
}
