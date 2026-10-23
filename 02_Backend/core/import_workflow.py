from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import ImportBatch, ImportedRecord, Transaction, AccountHead, FinancialYear, Unit, InternalSection, OutflowNature
from .import_services import _read_tabular_rows, apply_ngl_head_mapping


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _parse_amount(value):
    try:
        return Decimal(str(value).replace(',', '').strip())
    except (InvalidOperation, AttributeError):
        return None


def _resolve_name(model, raw):
    if not raw:
        return None
    text = str(raw).strip()
    return model.objects.filter(is_active=True).filter(name__iexact=text).first() or model.objects.filter(is_active=True).filter(code__iexact=text).first()


def validate_frontend_batch(batch, mapping):
    valid = failed = duplicate = 0
    for record in batch.records.all().order_by('original_row_number'):
        data = record.row_data
        errors = []
        parsed_date = _parse_date(data.get(mapping.get('date')))
        amount = _parse_amount(data.get(mapping.get('amount')))
        head_raw = data.get(mapping.get('head_code'))
        head = None
        if not parsed_date:
            errors.append('Invalid or missing Date.')
        if amount is None or amount <= 0:
            errors.append('Invalid or non-positive Amount.')
        if not head_raw:
            errors.append('Missing Account Head.')
        else:
            mapped = apply_ngl_head_mapping(head_raw)
            head = AccountHead.objects.filter(account=batch.account, name__iexact=mapped).first()
            if not head:
                errors.append(f'Unknown Account Head: {head_raw}.')
        if parsed_date and not FinancialYear.objects.filter(start_date__lte=parsed_date, end_date__gte=parsed_date).exists():
            errors.append(f'No Financial Year covers {parsed_date}.')
        unit_raw = data.get(mapping.get('unit')) if mapping.get('unit') else None
        section_raw = data.get(mapping.get('section')) if mapping.get('section') else None
        if unit_raw and not _resolve_name(Unit, unit_raw):
            errors.append(f'Unknown Unit: {unit_raw}.')
        if section_raw and not _resolve_name(InternalSection, section_raw):
            errors.append(f'Unknown Internal Section: {section_raw}.')
        if parsed_date and amount is not None and head:
            dup = Transaction.objects.filter(account=batch.account, transaction_date=parsed_date, amount=amount, account_head=head).exclude(status=Transaction.Status.SOFT_DELETED).exists()
            if dup:
                record.duplicate_status = True
                errors.append('Potential duplicate found.')
        if errors:
            record.validation_status = ImportedRecord.Status.DUPLICATE if record.duplicate_status else ImportedRecord.Status.INVALID
            record.error_message = '; '.join(errors)
            if record.duplicate_status: duplicate += 1
            else: failed += 1
        else:
            record.validation_status = ImportedRecord.Status.VALID
            record.error_message = ''
            valid += 1
        record.save(update_fields=['validation_status', 'error_message', 'duplicate_status'])
    batch.status = ImportBatch.Status.PREVIEWED
    batch.failed_rows = failed
    batch.duplicate_rows = duplicate
    batch.save(update_fields=['status', 'failed_rows', 'duplicate_rows'])
    return {'valid': valid, 'failed': failed, 'duplicates': duplicate}


def commit_frontend_batch(batch, mapping):
    if batch.status != ImportBatch.Status.PREVIEWED:
        raise ValidationError('Batch must be previewed and validated before commit.')
    imported = 0
    with transaction.atomic():
        for record in batch.records.filter(validation_status=ImportedRecord.Status.VALID).order_by('original_row_number'):
            data = record.row_data
            tx_date = _parse_date(data.get(mapping.get('date')))
            amount = _parse_amount(data.get(mapping.get('amount')))
            head = AccountHead.objects.get(account=batch.account, name__iexact=apply_ngl_head_mapping(data.get(mapping.get('head_code'))))
            fy = FinancialYear.objects.get(start_date__lte=tx_date, end_date__gte=tx_date)
            direction_raw = str(data.get(mapping.get('direction')) or 'OUTFLOW').strip().upper() if mapping.get('direction') else 'OUTFLOW'
            direction = Transaction.Direction.INFLOW if direction_raw in ('INFLOW', 'IN', 'RECEIPT', 'RECEIPTS') else Transaction.Direction.OUTFLOW
            unit = _resolve_name(Unit, data.get(mapping.get('unit'))) if mapping.get('unit') else None
            section = _resolve_name(InternalSection, data.get(mapping.get('section'))) if mapping.get('section') else None
            desc = str(data.get(mapping.get('description')) or '') if mapping.get('description') else ''
            ref = str(data.get(mapping.get('reference')) or '') if mapping.get('reference') else ''
            nature = None
            nature_raw = data.get(mapping.get('nature')) if mapping.get('nature') else None
            if nature_raw:
                nature = _resolve_name(OutflowNature, nature_raw)
            tx = Transaction.objects.create(
                account=batch.account, financial_year=fy, account_head=head,
                transaction_date=tx_date, direction=direction, amount=amount,
                unit=unit, internal_section=section,
                payee_or_source='Imported Record', description=desc,
                remarks=desc, reference=ref, outflow_nature=nature,
                status=Transaction.Status.ACTIVE, created_by=batch.imported_by,
                is_historical=True,
            )
            if unit:
                tx.transaction_units.add(unit)
            if section:
                tx.transaction_sections.add(section)
            record.target_transaction = tx
            record.validation_status = ImportedRecord.Status.IMPORTED
            record.save(update_fields=['target_transaction', 'validation_status'])
            imported += 1
        batch.imported_rows = imported
        batch.status = ImportBatch.Status.COMPLETED
        batch.save(update_fields=['imported_rows', 'status'])
    return imported
