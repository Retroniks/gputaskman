"""Current GPU activity only. Older and unavailable values are not active."""

def active_summary(rows):
    active = [r for r in rows if r.get('gpu_value_state') == 'current'
              and isinstance(r.get('gpu_pct'), (int, float))
              and not isinstance(r.get('gpu_pct'), bool)
              and r['gpu_pct'] > 0]
    active.sort(key=lambda r: (-r['gpu_pct'], str(r.get('name') or ''), r.get('pid', 0)))
    best = active[0] if active else None
    return {'gpu_active_count': len(active),
            'gpu_top_process': {'pid': best['pid'], 'name': best.get('name') or f"PID {best['pid']}",
                                'gpu_pct': best['gpu_pct']} if best else None}
