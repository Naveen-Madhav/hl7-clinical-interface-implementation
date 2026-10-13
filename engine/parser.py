"""Small, delimiter-aware parser for HL7 ER7 messages."""

from __future__ import annotations

import re
from typing import Dict, List, Optional


class HL7Field:
    def __init__(self, raw_value: str = "", component_sep: str = "^", subcomponent_sep: str = "&", repetition_sep: str = "~") -> None:
        self.component_sep = component_sep
        self.subcomponent_sep = subcomponent_sep
        self.repetition_sep = repetition_sep
        self.raw_value = raw_value

    def get_component(self, comp_idx: int = 1, rep_idx: int = 0) -> str:
        if comp_idx < 1 or rep_idx < 0:
            return ""
        repetitions = self.raw_value.split(self.repetition_sep)
        if rep_idx >= len(repetitions):
            return ""
        components = repetitions[rep_idx].split(self.component_sep)
        return components[comp_idx - 1] if comp_idx <= len(components) else ""

    def set_component(self, comp_idx: int, value: str, rep_idx: int = 0) -> None:
        if comp_idx < 1 or rep_idx < 0:
            raise ValueError("HL7 component and repetition indexes are invalid")
        repetitions = self.raw_value.split(self.repetition_sep) if self.raw_value else [""]
        while len(repetitions) <= rep_idx:
            repetitions.append("")
        components = repetitions[rep_idx].split(self.component_sep)
        while len(components) < comp_idx:
            components.append("")
        components[comp_idx - 1] = str(value)
        repetitions[rep_idx] = self.component_sep.join(components)
        self.raw_value = self.repetition_sep.join(repetitions)

    def __str__(self) -> str:
        return self.raw_value


class HL7Segment:
    def __init__(self, segment_name: str, fields: Optional[List[str]] = None, field_sep: str = "|", encoding_chars: str = "^~\\&") -> None:
        self.name = segment_name.strip().upper()
        self.field_sep = field_sep
        self.encoding_chars = encoding_chars
        self.comp_sep = encoding_chars[0] if len(encoding_chars) > 0 else "^"
        self.rep_sep = encoding_chars[1] if len(encoding_chars) > 1 else "~"
        self.sub_sep = encoding_chars[3] if len(encoding_chars) > 3 else "&"
        self.fields: List[str] = list(fields or [])

    def get_field_raw(self, field_num: int) -> str:
        if field_num < 1:
            return ""
        if self.name == "MSH":
            if field_num == 1:
                return self.field_sep
            if field_num == 2:
                return self.encoding_chars
            field_num -= 2
        index = field_num - 1
        return self.fields[index] if index < len(self.fields) else ""

    def set_field_raw(self, field_num: int, value: str) -> None:
        if field_num < 1:
            raise ValueError("HL7 field indexes start at one")
        if self.name == "MSH":
            if field_num == 1:
                self.field_sep = value
                return
            if field_num == 2:
                self.encoding_chars = value
                self.comp_sep = value[0] if len(value) > 0 else "^"
                self.rep_sep = value[1] if len(value) > 1 else "~"
                self.sub_sep = value[3] if len(value) > 3 else "&"
                return
            field_num -= 2
        index = field_num - 1
        while len(self.fields) <= index:
            self.fields.append("")
        self.fields[index] = str(value)

    def get_component(self, field_num: int, comp_num: int = 1) -> str:
        field = HL7Field(self.get_field_raw(field_num), self.comp_sep, self.sub_sep, self.rep_sep)
        return field.get_component(comp_num)

    def set_component(self, field_num: int, comp_num: int, value: str) -> None:
        field = HL7Field(self.get_field_raw(field_num), self.comp_sep, self.sub_sep, self.rep_sep)
        field.set_component(comp_num, value)
        self.set_field_raw(field_num, str(field))

    def to_er7(self) -> str:
        if self.name == "MSH":
            return self.name + self.field_sep + self.encoding_chars + self.field_sep + self.field_sep.join(self.fields)
        return self.name + self.field_sep + self.field_sep.join(self.fields)

    def __str__(self) -> str:
        return self.to_er7()


class HL7Message:
    _FIELD_PATH = re.compile(r"^([A-Z0-9]{3})(?:\((\d+)\))?-(\d+)(?:\.(\d+))?$")

    def __init__(self, segments: Optional[List[HL7Segment]] = None) -> None:
        self.segments: List[HL7Segment] = list(segments or [])
        self.properties: Dict[str, str] = {}

    def get_segment(self, name: str, index: int = 0) -> Optional[HL7Segment]:
        matches = [segment for segment in self.segments if segment.name == name.upper()]
        return matches[index] if 0 <= index < len(matches) else None

    def get_segments(self, name: str) -> List[HL7Segment]:
        return [segment for segment in self.segments if segment.name == name.upper()]

    def has_segment(self, name: str) -> bool:
        return self.get_segment(name) is not None

    def get_segment_count(self, name: str) -> int:
        return len(self.get_segments(name))

    def add_segment(self, segment: HL7Segment) -> None:
        self.segments.append(segment)

    def insert_segment(self, index: int, segment: HL7Segment) -> None:
        self.segments.insert(index, segment)

    def get_field(self, path: str) -> str:
        match = self._FIELD_PATH.match(path.strip().upper())
        if not match:
            return ""
        segment = self.get_segment(match.group(1), int(match.group(2) or 0))
        if segment is None:
            return ""
        field_num = int(match.group(3))
        component = match.group(4)
        return segment.get_component(field_num, int(component)) if component else segment.get_field_raw(field_num)

    def set_field(self, path: str, value: str) -> None:
        match = self._FIELD_PATH.match(path.strip().upper())
        if not match:
            raise ValueError(f"Invalid HL7 field path: {path}")
        segment = self.get_segment(match.group(1), int(match.group(2) or 0))
        if segment is None:
            raise ValueError(f"Cannot set a field on missing segment {match.group(1)}")
        field_num = int(match.group(3))
        component = match.group(4)
        if component:
            segment.set_component(field_num, int(component), value)
        else:
            segment.set_field_raw(field_num, value)

    def get_property(self, key: str, default: str = "") -> str:
        return self.properties.get(key, default)

    def set_property(self, key: str, value: str) -> None:
        self.properties[key] = str(value)

    def to_er7(self, segment_sep: str = "\r") -> str:
        return segment_sep.join(segment.to_er7() for segment in self.segments) + segment_sep

    def __str__(self) -> str:
        return self.to_er7()


def parse_hl7_message(raw_text: str) -> HL7Message:
    if not isinstance(raw_text, str) or not raw_text.strip("\x0b\x1c\r\n "):
        raise ValueError("HL7 message is empty")

    cleaned = raw_text.strip("\x0b\x1c\r\n ")
    lines = [line for line in re.split(r"[\r\n]+", cleaned) if line]
    if not lines:
        raise ValueError("HL7 message contains no segments")

    first = lines[0]
    field_sep = first[3] if first.startswith("MSH") and len(first) > 3 else "|"
    encoding_chars = "^~\\&"
    if first.startswith("MSH") and len(first) > 4:
        encoding_chars = first[4:].split(field_sep, 1)[0] or encoding_chars

    segments: List[HL7Segment] = []
    for line in lines:
        if line[:3] == "MSH":
            if len(line) < 5:
                raise ValueError("MSH segment is missing its encoding characters")
            separator = line[3]
            parts = line[4:].split(separator)
            segments.append(HL7Segment("MSH", parts[1:], field_sep=separator, encoding_chars=parts[0]))
        else:
            parts = line.split(field_sep)
            if not parts[0]:
                raise ValueError("HL7 message contains a segment without a name")
            segments.append(HL7Segment(parts[0], parts[1:], field_sep, encoding_chars))
    return HL7Message(segments)
