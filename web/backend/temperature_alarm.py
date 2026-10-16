"""Persistent outlet-temperature thresholds and edge-triggered alarms."""

from datetime import datetime
import math

from models import AlarmLog, TemperatureThreshold


ALARM_TYPES = ("outlet_temperature_low", "outlet_temperature_high")


class TemperatureThresholdError(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.code = "invalid_temperature_thresholds"
        self.message = message
        self.http_status = 422


class TemperatureAlarmService:
    def __init__(self, session_factory, defaults=(0.0, 60.0)):
        self.session_factory = session_factory
        self.defaults = (float(defaults[0]), float(defaults[1]))

    def _get_or_create(self, session):
        record = session.get(TemperatureThreshold, 1)
        if record is None:
            record = TemperatureThreshold(
                id=1,
                minimum_c=self.defaults[0],
                maximum_c=self.defaults[1],
                updated_at=datetime.now(),
            )
            session.add(record)
            session.flush()
        return record

    @staticmethod
    def _serialize_thresholds(record):
        return {
            "minimum_c": record.minimum_c,
            "maximum_c": record.maximum_c,
            "updated_at": record.updated_at.isoformat(timespec="seconds"),
        }

    @staticmethod
    def _validate(minimum_c, maximum_c):
        try:
            minimum = float(minimum_c)
            maximum = float(maximum_c)
        except (TypeError, ValueError) as exc:
            raise TemperatureThresholdError("温度上下限必须是数字") from exc
        if not math.isfinite(minimum) or not math.isfinite(maximum):
            raise TemperatureThresholdError("温度上下限必须是有限数字")
        if minimum < -55.0 or maximum > 125.0:
            raise TemperatureThresholdError("温度上下限必须位于 -55.0 到 125.0 °C")
        if minimum >= maximum:
            raise TemperatureThresholdError("温度下限必须小于上限")
        return minimum, maximum

    def get_thresholds(self):
        with self.session_factory() as session:
            record = self._get_or_create(session)
            session.commit()
            session.refresh(record)
            return self._serialize_thresholds(record)

    def update_thresholds(self, minimum_c, maximum_c):
        minimum, maximum = self._validate(minimum_c, maximum_c)
        with self.session_factory() as session:
            record = self._get_or_create(session)
            record.minimum_c = minimum
            record.maximum_c = maximum
            record.updated_at = datetime.now()
            session.commit()
            session.refresh(record)
            return self._serialize_thresholds(record)

    @staticmethod
    def _serialize_alarm(record):
        return {
            "id": record.id,
            "device_id": record.device_id,
            "timestamp": record.timestamp.isoformat(timespec="seconds"),
            "alarm_type": record.alarm_type,
            "message": record.msg,
            "value": record.value,
            "threshold": record.threshold,
            "active": bool(record.active),
            "status": "active" if record.active else "cleared",
            "cleared_at": record.cleared_at.isoformat(timespec="seconds") if record.cleared_at else None,
        }

    def process_temp2(self, device_id: str, value, observed_at: datetime):
        try:
            temperature = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(temperature):
            return None
        with self.session_factory() as session:
            thresholds = self._get_or_create(session)
            if temperature < thresholds.minimum_c:
                region = "outlet_temperature_low"
                threshold = thresholds.minimum_c
                message = "出水温度低于设定下限"
            elif temperature > thresholds.maximum_c:
                region = "outlet_temperature_high"
                threshold = thresholds.maximum_c
                message = "出水温度超过设定上限"
            else:
                region = None
                threshold = None
                message = ""

            active = (
                session.query(AlarmLog)
                .filter(
                    AlarmLog.device_id == device_id,
                    AlarmLog.alarm_type.in_(ALARM_TYPES),
                    AlarmLog.active.is_(True),
                )
                .order_by(AlarmLog.timestamp.desc())
                .first()
            )
            if active is not None and active.alarm_type == region:
                session.commit()
                return None
            if active is not None:
                active.active = False
                active.cleared_at = observed_at
                if region is None:
                    session.commit()
                    session.refresh(active)
                    return self._serialize_alarm(active)
            if region is None:
                session.commit()
                return None
            record = AlarmLog(
                device_id=device_id,
                timestamp=observed_at,
                alarm_type=region,
                code=1 if region.endswith("high") else 2,
                level="warn",
                msg=message,
                value=temperature,
                threshold=threshold,
                active=True,
                raw_json="{}",
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._serialize_alarm(record)

    def query_alarms(self, start=None, end=None, limit=50, offset=0):
        if not isinstance(limit, int) or not 1 <= limit <= 2000 or not isinstance(offset, int) or offset < 0:
            raise TemperatureThresholdError("分页参数超出允许范围")
        with self.session_factory() as session:
            query = session.query(AlarmLog).filter(AlarmLog.alarm_type.in_(ALARM_TYPES))
            if start is not None:
                query = query.filter(AlarmLog.timestamp >= start)
            if end is not None:
                query = query.filter(AlarmLog.timestamp <= end)
            total = query.count()
            records = query.order_by(AlarmLog.timestamp.desc()).offset(offset).limit(limit).all()
            rows = [self._serialize_alarm(record) for record in records]
            return {"count": len(rows), "total": total, "rows": rows}
