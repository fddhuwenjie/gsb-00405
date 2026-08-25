from fastapi import HTTPException, status


class QualityInspectionException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)
    
    def __str__(self) -> str:
        return str(self.detail)


class SampleCodeDuplicateError(QualityInspectionException):
    def __init__(self, sample_code: str):
        super().__init__(detail=f"样品编号重复: {sample_code}")


class TestItemMissingError(QualityInspectionException):
    def __init__(self, missing_items: list):
        super().__init__(detail=f"检测项目缺失: {', '.join(missing_items)}")


class ReInspectionLinkError(QualityInspectionException):
    def __init__(self, detail: str):
        super().__init__(detail=f"复检关联错误: {detail}")


class RetentionDestroyedError(QualityInspectionException):
    def __init__(self, sample_code: str):
        super().__init__(detail=f"留样已销毁，无法复检: {sample_code}")


class ReleaseNotAllowedError(QualityInspectionException):
    def __init__(self, detail: str):
        super().__init__(detail=f"无法放行: {detail}", status_code=status.HTTP_403_FORBIDDEN)


class BatchNotFoundError(QualityInspectionException):
    def __init__(self, batch_no: str = None, batch_id: int = None):
        identifier = batch_no or f"ID={batch_id}"
        super().__init__(detail=f"批次不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class SampleNotFoundError(QualityInspectionException):
    def __init__(self, sample_code: str = None, sample_id: int = None):
        identifier = sample_code or f"ID={sample_id}"
        super().__init__(detail=f"样品不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class ReportNotFoundError(QualityInspectionException):
    def __init__(self, report_no: str = None, report_id: int = None):
        identifier = report_no or f"ID={report_id}"
        super().__init__(detail=f"报告不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class TestItemNotFoundError(QualityInspectionException):
    def __init__(self, item_code: str = None, item_id: int = None):
        identifier = item_code or f"ID={item_id}"
        super().__init__(detail=f"检测项不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class RetentionNotFoundError(QualityInspectionException):
    def __init__(self, sample_code: str = None):
        super().__init__(detail=f"留样记录不存在: {sample_code or ''}", status_code=status.HTTP_404_NOT_FOUND)


class ReInspectionNotFoundError(QualityInspectionException):
    def __init__(self, reinspection_code: str = None, reinspection_id: int = None):
        identifier = reinspection_code or f"ID={reinspection_id}"
        super().__init__(detail=f"复检记录不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class InvalidStatusError(QualityInspectionException):
    def __init__(self, current_status: str, expected_status: str):
        super().__init__(detail=f"状态无效: 当前状态为 {current_status}，期望状态为 {expected_status}")


class NoAvailableLocationError(QualityInspectionException):
    def __init__(self):
        super().__init__(detail="没有可用的留样位置")


class ExportError(QualityInspectionException):
    def __init__(self, detail: str):
        super().__init__(detail=f"导出失败: {detail}", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)


class RetentionNotExpiredError(QualityInspectionException):
    def __init__(self, sample_code: str, days_left: int):
        super().__init__(detail=f"留样未到期，剩余 {days_left} 天: {sample_code}")


class ArbitrationNotFoundError(QualityInspectionException):
    def __init__(self, arbitration_code: str = None, arbitration_id: int = None):
        identifier = arbitration_code or f"ID={arbitration_id}"
        super().__init__(detail=f"仲裁记录不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class ArbitrationPendingError(QualityInspectionException):
    def __init__(self, batch_no: str):
        super().__init__(detail=f"批次 {batch_no} 存在未完成的仲裁，无法放行", status_code=status.HTTP_403_FORBIDDEN)


class ArbitrationNotAllowedError(QualityInspectionException):
    def __init__(self, detail: str):
        super().__init__(detail=f"无法发起仲裁: {detail}")


class RegulatoryInspectionNotFoundError(QualityInspectionException):
    def __init__(self, inspection_code: str = None, inspection_id: int = None):
        identifier = inspection_code or f"ID={inspection_id}"
        super().__init__(detail=f"监管抽检记录不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class RegulatoryDifferenceNotFoundError(QualityInspectionException):
    def __init__(self, difference_code: str = None, difference_id: int = None):
        identifier = difference_code or f"ID={difference_id}"
        super().__init__(detail=f"监管差异单不存在: {identifier}", status_code=status.HTTP_404_NOT_FOUND)


class BatchFrozenError(QualityInspectionException):
    def __init__(self, batch_no: str, reason: str = None):
        msg = f"批次 {batch_no} 已被冻结，无法操作"
        if reason:
            msg += f"，冻结原因: {reason}"
        super().__init__(detail=msg, status_code=status.HTTP_403_FORBIDDEN)


class BatchNotFrozenError(QualityInspectionException):
    def __init__(self, batch_no: str):
        super().__init__(detail=f"批次 {batch_no} 未被冻结")


class BatchNotReleasedError(QualityInspectionException):
    def __init__(self, batch_no: str):
        super().__init__(detail=f"批次 {batch_no} 未被放行，无法撤销放行")


class InspectionAlreadyConfirmedError(QualityInspectionException):
    def __init__(self, inspection_code: str):
        super().__init__(detail=f"监管抽检记录 {inspection_code} 已确认，无法修改")
