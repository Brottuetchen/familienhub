package de.familienhub.app

import android.content.Context
import android.content.SharedPreferences

/** The list sections a widget can show. Keys match the data written by lib/services/home_widgets.dart. */
enum class Section(
    val key: String,
    val route: String,
    val labelRes: Int,
    val iconRes: Int,
    val container: Int,
    val head: Int,
    val icon: Int,
    val label: Int,
    val empty: Int,
    val rows: IntArray,
) {
    EVENTS("events", "/calendar", R.string.section_events, R.drawable.ic_widget_events,
        R.id.sec_events, R.id.sec_events_head, R.id.sec_events_icon, R.id.sec_events_label, R.id.sec_events_empty,
        intArrayOf(R.id.events_row_0, R.id.events_row_1, R.id.events_row_2, R.id.events_row_3, R.id.events_row_4,
            R.id.events_row_5, R.id.events_row_6, R.id.events_row_7, R.id.events_row_8, R.id.events_row_9,
            R.id.events_row_10, R.id.events_row_11, R.id.events_row_12, R.id.events_row_13)),
    TASKS("tasks", "/tasks", R.string.section_tasks, R.drawable.ic_widget_tasks,
        R.id.sec_tasks, R.id.sec_tasks_head, R.id.sec_tasks_icon, R.id.sec_tasks_label, R.id.sec_tasks_empty,
        intArrayOf(R.id.tasks_row_0, R.id.tasks_row_1, R.id.tasks_row_2, R.id.tasks_row_3, R.id.tasks_row_4,
            R.id.tasks_row_5, R.id.tasks_row_6, R.id.tasks_row_7, R.id.tasks_row_8, R.id.tasks_row_9,
            R.id.tasks_row_10, R.id.tasks_row_11, R.id.tasks_row_12, R.id.tasks_row_13)),
    SHOPPING("shopping", "/shopping", R.string.section_shopping, R.drawable.ic_widget_shopping,
        R.id.sec_shopping, R.id.sec_shopping_head, R.id.sec_shopping_icon, R.id.sec_shopping_label, R.id.sec_shopping_empty,
        intArrayOf(R.id.shopping_row_0, R.id.shopping_row_1, R.id.shopping_row_2, R.id.shopping_row_3, R.id.shopping_row_4,
            R.id.shopping_row_5, R.id.shopping_row_6, R.id.shopping_row_7, R.id.shopping_row_8, R.id.shopping_row_9,
            R.id.shopping_row_10, R.id.shopping_row_11, R.id.shopping_row_12, R.id.shopping_row_13));

    companion object {
        const val MAX_ROWS = 14
    }
}

/** Per-widget choice of sections for the configurable "Today" widget (own preferences file, never wiped by the app). */
object WidgetConfig {
    private const val FILE = "familienhub_widget_config"

    private fun prefs(context: Context): SharedPreferences = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    /** Selected sections in display order; default (not configured yet) is all three. */
    fun sections(context: Context, widgetId: Int): List<Section> {
        val raw = prefs(context).getString("sections_$widgetId", null) ?: return Section.values().toList()
        val chosen = raw.split(',').toSet()
        return Section.values().filter { it.key in chosen }.ifEmpty { Section.values().toList() }
    }

    fun save(context: Context, widgetId: Int, sections: Collection<Section>) {
        prefs(context).edit().putString("sections_$widgetId", sections.joinToString(",") { it.key }).apply()
    }

    fun delete(context: Context, widgetIds: IntArray) {
        val e = prefs(context).edit()
        widgetIds.forEach { e.remove("sections_$it") }
        e.apply()
    }
}
