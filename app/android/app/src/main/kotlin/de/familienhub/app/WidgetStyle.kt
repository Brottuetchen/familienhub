package de.familienhub.app

import android.appwidget.AppWidgetManager
import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.widget.RemoteViews
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Aussehen der Widgets im Stil des gewählten App-Themes (Werte schreibt lib/services/home_widgets.dart):
 * Kartenfarbe, Rahmen, Rundung, Schatten (keiner, weich, hart versetzt) und farbiger Kopf.
 * Der Hintergrund wird als Bild in Widget-Größe gezeichnet, weil RemoteViews keine dynamischen Formen kennt.
 */
object WidgetStyle {
    data class Style(
        val card: Int, val text: Int, val muted: Int, val accent: Int, val green: Int,
        val border: Int, val borderDp: Float, val radiusDp: Float, val shadow: String,
        val band: Int?, val onBand: Int,
    )

    private fun color(p: SharedPreferences, key: String, fallback: Long): Int =
        (p.getString(key, null)?.toLongOrNull() ?: fallback).toInt()

    fun read(p: SharedPreferences) = Style(
        card = color(p, "w_card", 0xF2151726),
        text = color(p, "w_text", 0xFFFFFFFF),
        muted = color(p, "w_muted", 0x99FFFFFF),
        accent = color(p, "w_accent", 0xFFA78BFA),
        green = color(p, "w_green", 0xFF2FB36D),
        border = color(p, "w_border", 0x2EFFFFFF),
        borderDp = p.getString("w_border_w", null)?.toFloatOrNull() ?: 1f,
        radiusDp = p.getString("w_radius", null)?.toFloatOrNull() ?: 20f,
        shadow = p.getString("w_shadow", null) ?: "none",
        band = p.getString("w_band", null)?.toLongOrNull()?.toInt(),
        onBand = color(p, "w_on_band", 0xFFFFFFFF),
    )

    /** Abstand für den Schatten (rechts/unten bei hartem, rundum bei weichem Schatten), in dp. */
    private fun shadowDp(s: Style) = when (s.shadow) { "hard" -> 4f; "soft" -> 6f; else -> 0f }

    /**
     * Zeichnet den Hintergrund und setzt Innenabstände, damit der Inhalt im Kartenbereich bleibt.
     * [bandDp] ist die Höhe des Kopfbereichs (nur bei Neo-Brutalism eingefärbt).
     */
    fun apply(context: Context, manager: AppWidgetManager, id: Int, views: RemoteViews, s: Style, bandDp: Float) {
        val d = context.resources.displayMetrics.density
        val opts = manager.getAppWidgetOptions(id)
        val wDp = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH, 0).takeIf { it > 0 } ?: 300
        val hDp = opts.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT, 0).takeIf { it > 0 } ?: 160
        // Bildgröße begrenzen (RemoteViews-Speicherlimit): höchstens ~1,5 Mio. Pixel
        val scale = min(d, sqrt(1_500_000f / (wDp * hDp)))
        val w = (wDp * scale).toInt().coerceAtLeast(1)
        val h = (hDp * scale).toInt().coerceAtLeast(1)
        val bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
        val c = Canvas(bmp)
        val sh = shadowDp(s) * scale
        val bw = s.borderDp * scale
        val r = s.radiusDp * scale
        val left = if (s.shadow == "soft") sh else bw / 2
        val top = if (s.shadow == "soft") sh / 2 else bw / 2
        val rect = RectF(left, top, w - sh - bw / 2, h - sh - bw / 2)
        val fill = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.FILL; color = s.card }

        when (s.shadow) {
            "hard" -> c.drawRoundRect(RectF(rect.left + sh, rect.top + sh, rect.right + sh, rect.bottom + sh), r, r,
                Paint(Paint.ANTI_ALIAS_FLAG).apply { color = s.border })
            "soft" -> c.drawRoundRect(rect, r, r, Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = s.card; setShadowLayer(sh, 0f, sh / 2, 0x33000000) })
        }
        c.drawRoundRect(rect, r, r, fill)
        if (s.band != null) {
            val clip = Path().apply { addRoundRect(rect, r, r, Path.Direction.CW) }
            c.save()
            c.clipPath(clip)
            val bandBottom = rect.top + bandDp * scale
            c.drawRect(rect.left, rect.top, rect.right, bandBottom, Paint().apply { color = s.band })
            if (bw > 0) c.drawRect(rect.left, bandBottom, rect.right, bandBottom + bw, Paint().apply { color = s.border })
            c.restore()
        }
        if (bw > 0) {
            c.drawRoundRect(rect, r, r, Paint(Paint.ANTI_ALIAS_FLAG).apply {
                style = Paint.Style.STROKE; strokeWidth = bw; color = s.border })
        }
        views.setImageViewBitmap(R.id.widget_bg, bmp)

        val pad = (14 * d).toInt()
        val extra = (shadowDp(s) * d).toInt()
        val border = (s.borderDp * d).toInt()
        views.setViewPadding(
            R.id.widget_content,
            pad + border + (if (s.shadow == "soft") extra else 0),
            border + (if (s.shadow == "soft") extra / 2 else 0),
            pad + border + extra,
            pad + border + extra,
        )
    }
}
