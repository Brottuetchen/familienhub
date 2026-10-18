package de.familienhub.app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.os.Bundle
import es.antonborri.home_widget.HomeWidgetPlugin
import es.antonborri.home_widget.HomeWidgetProvider

/** Base of all Familienhub widgets: subclasses only decide which sections a widget instance shows. */
abstract class SectionsWidgetProvider : HomeWidgetProvider() {
    protected abstract fun sectionsFor(context: Context, widgetId: Int): List<Section>

    /** Single-purpose widgets show the section in the header instead of a section heading. */
    protected open val single: Boolean get() = false

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray,
        widgetData: SharedPreferences,
    ) {
        for (id in appWidgetIds) {
            val views = SectionsRenderer.render(context, appWidgetManager, id, widgetData, sectionsFor(context, id), single)
            appWidgetManager.updateAppWidget(id, views)
        }
    }

    /** Size changed: redraw the background and re-fit the number of rows. */
    override fun onAppWidgetOptionsChanged(context: Context, appWidgetManager: AppWidgetManager, appWidgetId: Int, newOptions: Bundle) {
        super.onAppWidgetOptionsChanged(context, appWidgetManager, appWidgetId, newOptions)
        onUpdate(context, appWidgetManager, intArrayOf(appWidgetId), HomeWidgetPlugin.getData(context))
    }
}

/** "Heute": date header plus the sections chosen in [TodayWidgetConfigActivity] (default: all). */
class TodayWidgetProvider : SectionsWidgetProvider() {
    override fun sectionsFor(context: Context, widgetId: Int) = WidgetConfig.sections(context, widgetId)

    override fun onDeleted(context: Context, appWidgetIds: IntArray) {
        super.onDeleted(context, appWidgetIds)
        WidgetConfig.delete(context, appWidgetIds)
    }
}

class EventsWidgetProvider : SectionsWidgetProvider() {
    override val single get() = true
    override fun sectionsFor(context: Context, widgetId: Int) = listOf(Section.EVENTS)
}

class TasksWidgetProvider : SectionsWidgetProvider() {
    override val single get() = true
    override fun sectionsFor(context: Context, widgetId: Int) = listOf(Section.TASKS)
}

class ShoppingWidgetProvider : SectionsWidgetProvider() {
    override val single get() = true
    override fun sectionsFor(context: Context, widgetId: Int) = listOf(Section.SHOPPING)
}
