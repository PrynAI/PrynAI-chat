__all__ = ["trace_id"]
def trace_id() -> str:
    # simple placeholder until we thread a real trace header
    import uuid
    return f"trace-{uuid.uuid4()}"