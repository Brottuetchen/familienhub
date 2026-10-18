package de.familienhub.app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Typeface
import android.net.Uri
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.text.style.StyleSpan
import android.view.View
import android.widget.RemoteViews
import es.antonborri.home_widget.HomeWidgetLaunchIntent

/**
 * Renders the shared widget layout (R.layout.widget_sections) for any combination of sections.
 * Used by the Today (configurable), Events, Tasks and Shopping widgets, so they look identical.
 *
 * The number of rows per section follows the widget height ([allocateRows]); rows that do not fit are
 * summarised as "+N more".
 */
object SectionsRenderer {
    private const val HEADER_DP = 44f
    private const val ROW_DP = 24f
    private const val SECTION_HEAD_DP = 28f
    private const val FOOTER_DP = 16f
    private const val MEAL_DP = 18f
    private const val BOTTOM_PAD_DP = 12f

    /** One row of a list: [when] is only used by events (time or "tomorrow 19:30", empty for all-day). */
    data class Row(val whenText: String, val text: String)

    /**
     * Distributes [budget] rows over sections that have [counts] items (an empty section needs one row for
     * its empty-state text). Every section gets at least one row, then rows are handed out round-robin.
     */
    fun allocateRows(counts: List<Int>, budget: Int): IntArray {
        val need = counts.map { it.coerceAtLeast(1).coerceAtMost(Section.MAX_ROWS + 1) }
        val alloc = IntArray(counts.size) { 1 }
        var remaining = budget - counts.size
        while (remaining > 0) {
            var progressed = false
            for (i in alloc.indices) {
                if (remaining > 0 && alloc[i] < need[i] && alloc[i] < Section.MAX_ROWS) {
                    alloc[i]++
                    remaining--
                    progressed = true
                }
            }
            if (!progressed) break
        }
        return alloc
    }

    private fun parse(section: Section, data: SharedPreferences): List<Row> {
        val raw = data.getString("${section.key}_items", "") ?: ""
        if (raw.isEmpty()) return emptyList()
        return raw.split('\n').filter { it.isNotBlank() }.map {
            if (section == Section.EVENTS) {
                val parts = it.split('\t', limit = 2)
                if (parts.size == 2) Row(parts[0], parts[1]) else Row("", it)
            } else Row("", it)
        }
    }

    private fun rowText(section: Section, row: Row, style: WidgetStyle.Style): CharSequence {
        val sb = SpannableStringBuilder()
        val prefix = when {
            section == Section.EVENTS && row.whenText.isNotEmpty() -> row.whenText
            section == Section.EVENTS -> "●"
            section == Section.TASKS -> "○"
            else -> "•"
        }
        sb.append(prefix).append("  ")
        sb.setSpan(ForegroundColorSpan(style.accent), 0, prefix.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        if (section == Section.EVENTS && row.whenText.isNotEmpty()) {
            sb.setSpan(StyleSpan(Typeface.BOLD), 0, prefix.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
        }
        sb.append(row.text)
        return sb
    }

    private fun open(context: Context, route: String) =
        HomeWidgetLaunchIntent.getActivity(context, MainActivity::class.java, Uri.parse("familienhub://open?route=$route"))

    fun render(
        context: Context,
        manager: AppWidgetManager,
        id: Int,
        data: SharedPreferences,
        requested: List<Section>,
        /** true for the single-purpose widgets: the header carries the section icon and name. */
        single: Boolean,
    ): RemoteViews {
        val style = WidgetStyle.read(data)
        val loggedIn = !data.getString("widget_session", null).isNullOrEmpty()
        // Logged out: show only the first section with a sign-in hint
        val sections = if (loggedIn) requested else requested.take(1)
        val views = RemoteViews(context.packageName, R.layout.widget_sections)
        val headColor = if (style.band != null) style.onBand else style.accent

        // Header
        val title = when {
            !loggedIn -> if (single) context.getString(sections[0].labelRes) else "Familienhub"
            single -> data.getString("${sections[0].key}_label", null)?.takeIf { it.isNotEmpty() } ?: context.getString(sections[0].labelRes)
            else -> data.getString("today_title", null)?.takeIf { it.isNotEmpty() } ?: context.getString(R.string.widget_title_today)
        }
        views.setTextViewText(R.id.widget_title, title)
        views.setTextColor(R.id.widget_title, headColor)
        if (single) {
            views.setViewVisibility(R.id.header_icon, View.VISIBLE)
            views.setImageViewResource(R.id.header_icon, sections[0].iconRes)
            views.setInt(R.id.header_icon, "setColorFilter", headColor)
        } else {
            views.setViewVisibility(R.id.header_icon, View.GONE)
        }

        val meal = if (loggedIn && !single) data.getString("today_meal", "") ?: "" else ""
        views.setTextViewText(R.id.widget_meal, meal)
        views.setTextColor(R.id.widget_meal, style.muted)
        views.setViewVisibility(R.id.widget_meal, if (meal.isEmpty()) View.GONE else View.VISIBLE)

        val updatedKey = if (sections.size == 1 && sections[0] == Section.SHOPPING) "shopping_updated" else "today_updated"
        views.setTextViewText(R.id.widget_updated, if (loggedIn) data.getString(updatedKey, "") else "")
        views.setTextColor(R.id.widget_updated, style.muted)

        // Row budget from the widget height
        val opts = manager.getAppWidgetOptions(id)
        val hDp = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 0).takeIf { it > 0 } ?: 160
        val chrome = HEADER_DP + BOTTOM_PAD_DP + FOOTER_DP + style.borderDp * 2 + (if (meal.isEmpty()) 0f else MEAL_DP) +
            (if (single) 0f else SECTION_HEAD_DP * sections.size)
        val budget = ((hDp - chrome) / ROW_DP).toInt().coerceAtLeast(sections.size)

        val rows = sections.map { if (loggedIn) parse(it, data) else emptyList() }
        val alloc = allocateRows(rows.map { it.size }, budget)

        for (s in Section.values()) {
            val idx = sections.indexOf(s)
            if (idx < 0) {
                views.setViewVisibility(s.container, View.GONE)
                continue
            }
            views.setViewVisibility(s.container, View.VISIBLE)
            views.setViewVisibility(s.head, if (single) View.GONE else View.VISIBLE)
            val label = data.getString("${s.key}_label", null)?.takeIf { it.isNotEmpty() && s != Section.SHOPPING }
                ?: context.getString(s.labelRes)
            views.setTextViewText(s.label, label.uppercase())
            views.setTextColor(s.label, style.muted)
            views.setInt(s.icon, "setColorFilter", style.accent)

            val items = rows[idx]
            val shown = alloc[idx]
            if (items.isEmpty()) {
                val empty = if (loggedIn) data.getString("${s.key}_empty", "") ?: "" else context.getString(R.string.widget_login)
                views.setTextViewText(s.empty, empty)
                views.setTextColor(s.empty, style.muted)
                views.setViewVisibility(s.empty, View.VISIBLE)
            } else {
                views.setViewVisibility(s.empty, View.GONE)
            }
            val truncated = items.size > shown && shown >= 2
            for (i in 0 until Section.MAX_ROWS) {
                val rowId = s.rows[i]
                if (i >= shown || items.isEmpty() || i >= items.size) {
                    views.setViewVisibility(rowId, View.GONE)
                    continue
                }
                views.setViewVisibility(rowId, View.VISIBLE)
                if (truncated && i == shown - 1) {
                    views.setTextViewText(rowId, context.getString(R.string.widget_more, items.size - shown + 1))
                    views.setTextColor(rowId, style.muted)
                } else {
                    views.setTextViewText(rowId, rowText(s, items[i], style))
                    views.setTextColor(rowId, style.text)
                }
            }
            // Tapping a section opens the matching tab
            views.setOnClickPendingIntent(s.container, open(context, s.route))
        }

        WidgetStyle.apply(context, manager, id, views, style, bandDp = HEADER_DP + style.borderDp)
        val rootRoute = if (single) sections[0].route else "/today"
        views.setOnClickPendingIntent(R.id.widget_root, open(context, rootRoute))
        return views
    }
}
