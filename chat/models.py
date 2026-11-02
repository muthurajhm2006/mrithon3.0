from django.db import models
from django.conf import settings
from machines.models import Machine

class QuestionStatus(models.TextChoices):
    ANSWERED = 'ANSWERED', 'Answered'
    INSUFFICIENT_EVIDENCE = 'INSUFFICIENT_EVIDENCE', 'Insufficient Evidence'

class QuestionHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='question_histories'
    )
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name='question_histories'
    )
    question = models.TextField(help_text="Question submitted by engineer")
    answer = models.TextField(help_text="AI generated answer")
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of source citations with document ID, page number, filename, passage"
    )
    status = models.CharField(
        max_length=30,
        choices=QuestionStatus.choices,
        default=QuestionStatus.ANSWERED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Question History'
        verbose_name_plural = 'Question Histories'

    def __str__(self):
        return f"[{self.machine.model}] {self.question[:40]}... ({self.get_status_display()})"
