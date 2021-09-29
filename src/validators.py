from __future__ import annotations

import pytimeparse

from entities import Command
from exceptions import ValidationError
from utils.validation import valid_ttl


def clean_ttl(params: list[str]) -> int:
    ttl_str = " ".join(params)
    ttl = pytimeparse.parse(ttl_str)
    print("TTL", ttl)
    print("TTL STR", ttl_str)

    if ttl:
        ttl = int(ttl)
    else:
        ttl = int(ttl_str)

    if not valid_ttl(ttl):
        raise ValueError

    return ttl


class Validator:
    def validate(self, command: Command) -> None:
        raise NotImplementedError


class GcValidator(Validator):
    def validate(self, command: Command) -> None:
        print("COM", command)
        if not command.params:
            return

        try:
            ttl = clean_ttl(command.params)
        except (TypeError, ValueError):
            print("EXC!")
            raise ValidationError(
                'Please provide a "time to live" for messages as a valid '
                'integer between 0 and 172800 or a time string such as "1h30m" '
                '("2 days" max).\n'
                'E.g. "/gc 1h" to start removing new messages after one hour.'
            )

        command.params_clean.append(ttl)


class FwdValidator(Validator):
    def validate(self, command: Command) -> None:
        if not command.params:
            return

        try:
            ttl = clean_ttl(command.params)
        except (TypeError, ValueError):
            raise ValidationError(
                'Please provide a "time to live" for forwarded messages as a valid '
                'integer between 0 and 172800 or a time string such as "1h30m" '
                '("2 days" max).\n'
                'E.g. "/fwd 1h" to start removing forwarded messages after one hour.'
            )

        command.params_clean.append(ttl)


class RetryValidator(Validator):
    def validate(self, command: Command) -> None:
        if not command.params:
            return

        try:
            max_attempts = int(command.params[0])
            if not (1 <= max_attempts <= 1000):
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError(
                "Please provide a valid integer between 1 and 1000 for the "
                "<i>max_attempts</i> parameter."
            )

        command.params_clean.append(max_attempts)
