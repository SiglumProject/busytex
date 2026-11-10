"""Validated transformations for native compiler link commands."""
from pathlib import Path


def replace_link_inputs(command, replacements):
    """Preserve link order, including repeated static archives.

    Static archives can be repeated to resolve cycles. Individual objects and
    the output path must occur exactly once; missing inputs always fail.
    Return the original occurrence counts for the provenance record.
    """
    counts = {old: command.count(old) for old in replacements}
    for old, count in counts.items():
        if count == 0 or (Path(old).suffix != '.a' and count != 1):
            raise ValueError('Unexpected link input occurrence count: ' + old + ' (' + str(count) + ')')
    result = [replacements.get(value, value) for value in command]
    return result, counts
