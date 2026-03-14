from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Note: In practice, db is injected dynamically during evaluation
async def get_resource_spikes_impl(lookback_seconds: int, db: AsyncSession) -> str:
    """
    Checks for recent resource spikes (CPU or Memory) across all supervised containers in a given lookback window.
    Returns a summarized string of containers that exceeded normal operational thresholds.
    """
    query = text("""
        WITH stats AS (
            SELECT 
                c.reference_name,
                (s.cpu_stats->>'usage')::numeric AS cpu_usage,
                (s.memory_stats->>'usage')::numeric AS mem_usage,
                s.timestamp,
                FIRST_VALUE((s.cpu_stats->>'usage')::numeric) OVER w AS first_cpu,
                LAST_VALUE((s.cpu_stats->>'usage')::numeric) OVER w AS last_cpu,
                FIRST_VALUE((s.memory_stats->>'usage')::numeric) OVER w AS first_mem,
                LAST_VALUE((s.memory_stats->>'usage')::numeric) OVER w AS last_mem
            FROM container_metric_snapshots s
            JOIN containers c ON s.container_id = c.id
            WHERE s.timestamp >= NOW() - (:lookback * interval '1 second')
            WINDOW w AS (PARTITION BY c.id ORDER BY s.timestamp RANGE BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
        ),
        deltas AS (
            SELECT DISTINCT
                reference_name,
                COALESCE(last_cpu - first_cpu, 0) AS cpu_delta,
                COALESCE(last_mem - first_mem, 0) AS mem_delta
            FROM stats
        )
        SELECT reference_name, cpu_delta, mem_delta
        FROM deltas
        WHERE mem_delta > 10000 OR cpu_delta > 1000  -- Example thresholds
        ORDER BY mem_delta DESC, cpu_delta DESC
        LIMIT 15;
    """)
    
    result = await db.execute(query, {"lookback": lookback_seconds})
    rows = result.fetchall()
    
    if not rows:
        return f"No significant resource spikes detected in the last {lookback_seconds} seconds."
        
    summary_lines = [f"Spike thresholds exceeded in the last {lookback_seconds}s:"]
    for row in rows:
        summary_lines.append(f" - Container '{row.reference_name}': CPU Delta={row.cpu_delta}, Mem Delta={row.mem_delta}")
        
    return "\n".join(summary_lines)

@tool
async def get_resource_spikes(lookback_seconds: int) -> str:
    """
    Checks for recent resource spikes (CPU or Memory) across all supervised containers in a given lookback window.
    """
    # This acts as a placeholder for the agent's tool schema.
    # The actual execution should inject the DB session.
    pass
