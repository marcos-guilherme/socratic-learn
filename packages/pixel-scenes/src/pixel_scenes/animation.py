def frame_progress(frame_index: int, frame_count: int) -> float:
    if frame_count <= 1:
        return 1.0
    return frame_index / (frame_count - 1)
