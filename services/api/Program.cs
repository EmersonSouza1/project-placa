using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Npgsql;
using NpgsqlTypes;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = 16 * 1024);
builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower;
    options.SerializerOptions.UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow;
    options.SerializerOptions.RespectRequiredConstructorParameters = true;
});
builder.Services.AddSingleton(_ => NpgsqlDataSource.Create(
    builder.Configuration.GetConnectionString("Database")
    ?? throw new InvalidOperationException("ConnectionStrings__Database is required")));
builder.Services.AddSingleton<EventStore>();
builder.Services.AddSingleton<LatestPlateDetection>();
var app = builder.Build();
app.UseExceptionHandler(handler => handler.Run(async context =>
{
    context.Response.StatusCode = 503;
    await context.Response.WriteAsJsonAsync(new { error = "Service unavailable; retry using the same event_id." });
}));
var source = app.Services.GetRequiredService<NpgsqlDataSource>();
await using (var schema = source.CreateCommand(await File.ReadAllTextAsync(Path.Combine(AppContext.BaseDirectory, "schema.sql"))))
    await schema.ExecuteNonQueryAsync();

app.MapGet("/health", async (NpgsqlDataSource db, LatestPlateDetection detections, CancellationToken ct) =>
{
    await using var command = db.CreateCommand("SELECT 1");
    await command.ExecuteScalarAsync(ct);
    return Results.Ok(new { status = "ok", last_plate_detection = detections.Read() });
});

app.MapPost("/ocr-observations", (PlateDetection input, LatestPlateDetection detections) =>
{
    if (string.IsNullOrWhiteSpace(input.CameraId) || input.CameraId.Length > 80 ||
        input.Plate is null || !Regex.IsMatch(input.Plate, @"\A[A-Z]{3}(?:[0-9]{4}|[0-9][A-Z][0-9]{2})\z") ||
        !double.IsFinite(input.Confidence) || input.Confidence < 0.7 || input.Confidence > 1 ||
        input.DetectedAt == default || input.DetectedAt > DateTimeOffset.UtcNow.AddMinutes(1))
        return Results.BadRequest(new { error = "Invalid OCR observation." });
    detections.Update(input);
    return Results.NoContent();
});

app.MapPost("/dock-events", async (DockEvent input, EventStore store, CancellationToken ct) =>
{
    var error = input.Validate();
    if (error is not null) return Results.BadRequest(new { error });
    try
    {
        var created = await store.Save(input, ct);
        return created
            ? Results.Created($"/dock-events/{input.EventId}", new { event_id = input.EventId, duplicate = false })
            : Results.Ok(new { event_id = input.EventId, duplicate = true });
    }
    catch (EventConflictException ex) { return Results.Conflict(new { error = ex.Message }); }
    catch (PostgresException ex) when (ex.SqlState is PostgresErrorCodes.UniqueViolation or PostgresErrorCodes.CheckViolation)
    { return Results.Conflict(new { error = "Conflicting transition or timestamp for this visit." }); }
});

app.MapGet("/dock-events/{id:guid}", async (Guid id, NpgsqlDataSource db, CancellationToken ct) =>
{
    await using var command = db.CreateCommand("SELECT payload::text FROM dock_events WHERE event_id=$1");
    command.Parameters.AddWithValue(id);
    var result = await command.ExecuteScalarAsync(ct);
    return result is string json ? Results.Content(json, "application/json") : Results.NotFound();
});

app.MapGet("/dock-events", async (string? dock_id, int? limit, EventStore store, CancellationToken ct) =>
    Results.Content(await store.List(false, dock_id, limit, ct), "application/json"));
app.MapGet("/dock-stays", async (string? dock_id, int? limit, EventStore store, CancellationToken ct) =>
    Results.Content(await store.List(true, dock_id, limit, ct), "application/json"));
app.Run();

public sealed record PlateDetection(string CameraId, string Plate, double Confidence, DateTimeOffset DetectedAt);

// Diagnostic snapshot only: no dock event, visit, or database projection is created.
public sealed class LatestPlateDetection
{
    private readonly object gate = new();
    private PlateDetection? latest;
    public PlateDetection? Read() { lock (gate) return latest; }
    public void Update(PlateDetection input)
    {
        lock (gate)
            if (latest is null || input.DetectedAt > latest.DetectedAt)
                latest = input with { DetectedAt = input.DetectedAt.ToUniversalTime() };
    }
}

public sealed record DockEvent(Guid EventId, Guid VisitId, string CameraId, string DockId,
    Guid StreamId, long TrackId, string EventType, DateTimeOffset OccurredAt,
    string? Plate, double? PlateConfidence)
{
    public string? Validate()
    {
        if (EventId == Guid.Empty || VisitId == Guid.Empty || StreamId == Guid.Empty)
            return "event_id, visit_id and stream_id must be nonempty UUIDs.";
        if (string.IsNullOrWhiteSpace(CameraId) || CameraId.Length > 80 || string.IsNullOrWhiteSpace(DockId) || DockId.Length > 80)
            return "camera_id and dock_id must have 1..80 characters.";
        if (TrackId < 0 || OccurredAt == default) return "track_id and occurred_at are required and must be valid.";
        if (EventType is not ("entered" or "observed_inside" or "exited" or "tracking_lost"))
            return "Unsupported event_type.";
        if ((Plate is null) != (PlateConfidence is null)) return "plate and plate_confidence must be supplied together.";
        if (Plate is not null && !Regex.IsMatch(Plate, @"\A[A-Z]{3}(?:[0-9]{4}|[0-9][A-Z][0-9]{2})\z"))
            return "Invalid Brazilian plate format.";
        if (PlateConfidence is double confidence && (!double.IsFinite(confidence) || confidence < 0 || confidence > 1))
            return "plate_confidence must be between 0 and 1.";
        return null;
    }
}

public sealed class EventConflictException(string message) : Exception(message);

public sealed class EventStore(NpgsqlDataSource source)
{
    private static readonly JsonSerializerOptions JsonOptions = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };

    public async Task<bool> Save(DockEvent input, CancellationToken ct)
    {
        // Canonicalize the timestamp, allowing the same instant with a different UTC offset.
        var payload = JsonSerializer.Serialize(input with { OccurredAt = input.OccurredAt.ToUniversalTime() }, JsonOptions);
        await using var connection = await source.OpenConnectionAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        // Serialize updates for a visit; event PK also handles concurrent duplicate requests.
        await using (var gate = new NpgsqlCommand("SELECT pg_advisory_xact_lock(hashtextextended($1,0))", connection, transaction))
        {
            gate.Parameters.AddWithValue(input.VisitId.ToString());
            await gate.ExecuteNonQueryAsync(ct);
        }
        await using (var existing = new NpgsqlCommand("SELECT payload = $2::jsonb FROM dock_events WHERE event_id=$1", connection, transaction))
        {
            existing.Parameters.AddWithValue(input.EventId);
            existing.Parameters.AddWithValue(payload);
            var same = await existing.ExecuteScalarAsync(ct);
            if (same is bool equal)
            {
                if (!equal) throw new EventConflictException("event_id already exists with different content.");
                await transaction.CommitAsync(ct);
                return false;
            }
        }
        await using (var identity = new NpgsqlCommand("""
            SELECT EXISTS(SELECT 1 FROM dock_events WHERE visit_id=$1 AND
              (camera_id<>$2 OR dock_id<>$3 OR stream_id<>$4 OR track_id<>$5))
            """, connection, transaction))
        {
            identity.Parameters.AddWithValue(input.VisitId);
            identity.Parameters.AddWithValue(input.CameraId);
            identity.Parameters.AddWithValue(input.DockId);
            identity.Parameters.AddWithValue(input.StreamId);
            identity.Parameters.AddWithValue(input.TrackId);
            if (await identity.ExecuteScalarAsync(ct) is true)
                throw new EventConflictException("visit_id belongs to a different camera, dock or track.");
        }
        await using (var insert = new NpgsqlCommand("""
            INSERT INTO dock_events(event_id,visit_id,camera_id,dock_id,stream_id,track_id,
                                    event_type,occurred_at,plate,plate_confidence,payload)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """, connection, transaction))
        {
            insert.Parameters.AddWithValue(input.EventId);
            insert.Parameters.AddWithValue(input.VisitId);
            insert.Parameters.AddWithValue(input.CameraId);
            insert.Parameters.AddWithValue(input.DockId);
            insert.Parameters.AddWithValue(input.StreamId);
            insert.Parameters.AddWithValue(input.TrackId);
            insert.Parameters.AddWithValue(input.EventType);
            insert.Parameters.AddWithValue(input.OccurredAt.ToUniversalTime());
            insert.Parameters.AddWithValue(NpgsqlDbType.Text, (object?)input.Plate ?? DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.Double, (object?)input.PlateConfidence ?? DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.Jsonb, payload);
            await insert.ExecuteNonQueryAsync(ct);
        }
        await using (var project = new NpgsqlCommand("""
            WITH events AS (SELECT * FROM dock_events WHERE visit_id=$1),
            timing AS (
              SELECT min(occurred_at) FILTER(WHERE event_type IN ('entered','observed_inside')) AS started_at,
                     min(occurred_at) FILTER(WHERE event_type IN ('exited','tracking_lost')) AS ended_at,
                     max(event_type) FILTER(WHERE event_type IN ('entered','observed_inside')) AS start_type,
                     max(event_type) FILTER(WHERE event_type IN ('exited','tracking_lost')) AS end_type
              FROM events
            ), best AS (
              SELECT plate,plate_confidence FROM events WHERE plate IS NOT NULL
              ORDER BY occurred_at DESC,plate_confidence DESC LIMIT 1
            )
            INSERT INTO dock_stays(visit_id,camera_id,dock_id,stream_id,track_id,started_at,ended_at,
                                   start_type,end_type,status,duration_seconds,plate,plate_confidence)
            SELECT e.visit_id,e.camera_id,e.dock_id,e.stream_id,e.track_id,t.started_at,t.ended_at,
                   t.start_type,t.end_type,
                   CASE WHEN t.started_at IS NULL THEN 'awaiting_start'
                        WHEN t.end_type='tracking_lost' THEN 'interrupted'
                        WHEN t.ended_at IS NULL THEN 'open' ELSE 'completed' END,
                   CASE WHEN t.start_type='entered' AND t.end_type='exited'
                        THEN extract(epoch FROM t.ended_at-t.started_at) ELSE NULL END,
                   b.plate,b.plate_confidence
            FROM (SELECT * FROM events LIMIT 1) e CROSS JOIN timing t LEFT JOIN best b ON true
            ON CONFLICT(visit_id) DO UPDATE SET
              started_at=excluded.started_at,ended_at=excluded.ended_at,
              start_type=excluded.start_type,end_type=excluded.end_type,status=excluded.status,
              duration_seconds=excluded.duration_seconds,plate=excluded.plate,
              plate_confidence=excluded.plate_confidence,updated_at=now()
            """, connection, transaction))
        {
            project.Parameters.AddWithValue(input.VisitId);
            await project.ExecuteNonQueryAsync(ct);
        }
        await transaction.CommitAsync(ct);
        return true;
    }

    public async Task<string> List(bool stays, string? dock, int? limit, CancellationToken ct)
    {
        // Table/order names are fixed internal constants; user values are parameters.
        var table = stays ? "dock_stays" : "dock_events";
        var order = stays ? "updated_at DESC,visit_id" : "occurred_at DESC,event_id";
        await using var command = source.CreateCommand($"""
            SELECT coalesce(jsonb_agg(to_jsonb(items)), '[]'::jsonb)::text
            FROM (SELECT * FROM {table} WHERE ($1::text IS NULL OR dock_id=$1)
                  ORDER BY {order} LIMIT $2) items
            """);
        command.Parameters.AddWithValue(NpgsqlDbType.Text, (object?)dock ?? DBNull.Value);
        command.Parameters.AddWithValue(Math.Clamp(limit ?? 100, 1, 500));
        return (string)(await command.ExecuteScalarAsync(ct))!;
    }
}
