from django.db.models import Count, Q

from .forms import DocumentReviewForm
from .models import HealthcareFacility, PractitionerProfile, RegistryDocument
from .services import apply_document_review_outcome


def review_registry_document(document: RegistryDocument, form: DocumentReviewForm, user):
    if document.review_status != RegistryDocument.ReviewStatus.PENDING:
        return document
    document.review_status = form.cleaned_data["review_status"]
    document.review_notes = form.cleaned_data.get("review_notes", "")
    document.reviewed_by = user
    from django.utils import timezone

    document.reviewed_at = timezone.now()
    document.save(update_fields=["review_status", "review_notes", "reviewed_by", "reviewed_at"])
    apply_document_review_outcome(document, user)
    return document


def group_documents_by_subject(documents):
    """Group a queryset of RegistryDocument rows under their practitioner or facility."""
    groups = {}
    order = []
    for doc in documents:
        if doc.practitioner_id:
            key = ("practitioner", doc.practitioner_id)
            label = str(doc.practitioner)
            subject = doc.practitioner
            detail_url_name = "regulator_practitioner_detail"
            detail_pk = doc.practitioner_id
        elif doc.facility_id:
            key = ("facility", doc.facility_id)
            label = str(doc.facility)
            subject = doc.facility
            detail_url_name = "regulator_facility_detail"
            detail_pk = doc.facility_id
        else:
            key = ("orphan", doc.pk)
            label = "Unlinked submission"
            subject = None
            detail_url_name = None
            detail_pk = None

        if key not in groups:
            groups[key] = {
                "key": key,
                "label": label,
                "subject": subject,
                "subject_type": key[0],
                "detail_url_name": detail_url_name,
                "detail_pk": detail_pk,
                "documents": [],
                "pending_count": 0,
            }
            order.append(key)
        groups[key]["documents"].append(doc)
        if doc.review_status == RegistryDocument.ReviewStatus.PENDING:
            groups[key]["pending_count"] += 1

    return [groups[k] for k in order]


def build_dossier_context(documents, *, open_document_id=None):
    """Prepare document rows with optional inline review forms for a subject dossier page."""
    rows = []
    for doc in documents:
        prefix = f"doc_{doc.pk}"
        is_pending = doc.review_status == RegistryDocument.ReviewStatus.PENDING
        is_open = str(open_document_id) == str(doc.pk) if open_document_id else is_pending
        rows.append(
            {
                "document": doc,
                "form": DocumentReviewForm(prefix=prefix) if is_pending else None,
                "is_open": is_open,
                "is_locked": not is_pending,
            }
        )
    pending = sum(1 for row in rows if row["document"].review_status == RegistryDocument.ReviewStatus.PENDING)
    return {"document_rows": rows, "pending_document_count": pending, "total_document_count": len(rows)}


def annotate_practitioner_list(queryset):
    return queryset.annotate(
        document_count=Count("documents", distinct=True),
        pending_document_count=Count(
            "documents",
            filter=Q(documents__review_status=RegistryDocument.ReviewStatus.PENDING),
            distinct=True,
        ),
    )


def annotate_facility_list(queryset):
    return queryset.annotate(
        document_count=Count("documents", distinct=True),
        pending_document_count=Count(
            "documents",
            filter=Q(documents__review_status=RegistryDocument.ReviewStatus.PENDING),
            distinct=True,
        ),
    )
