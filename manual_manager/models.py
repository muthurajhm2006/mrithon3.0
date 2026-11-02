from django.db import models
from django.core.exceptions import ValidationError
from machines.models import Machine
import os

def validate_pdf_file(value):
    ext = os.path.splitext(value.name)[1]
    if ext.lower() != '.pdf':
        raise ValidationError('Only PDF files are supported.')
    if value.size > 25 * 1024 * 1024:
        raise ValidationError('File size exceeds the 25MB maximum limit.')

class Manual(models.Model):
    document_id = models.CharField(
        max_length=50,
        help_text="Document ID (e.g., HP-OPS-01, HP-MNT-01, AC-OM-01)"
    )
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name='manuals'
    )
    revision = models.CharField(
        max_length=20,
        default="1.0",
        help_text="Manual revision version (e.g., 1.0)"
    )
    title = models.CharField(
        max_length=255,
        help_text="Document title"
    )
    pdf_filename = models.CharField(
        max_length=255,
        help_text="Original PDF filename"
    )
    pdf_file = models.FileField(
        upload_to='manuals_uploaded/',
        validators=[validate_pdf_file],
        help_text="Uploaded PDF document"
    )
    page_count = models.PositiveIntegerField(
        default=0,
        help_text="Total extracted pages"
    )
    total_chunks = models.PositiveIntegerField(
        default=0,
        help_text="Total indexed passages/chunks"
    )
    is_indexed = models.BooleanField(
        default=False,
        help_text="Whether this manual is currently indexed in the vector store"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['machine', 'document_id']
        unique_together = ('machine', 'document_id', 'revision')
        verbose_name = 'Manual'
        verbose_name_plural = 'Manuals'

    def __str__(self):
        return f"{self.document_id} Rev {self.revision} - {self.machine.model} ({self.pdf_filename})"
