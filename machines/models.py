from django.db import models

class Machine(models.Model):
    machine_id = models.CharField(
        max_length=50,
        primary_key=True,
        help_text="Unique Machine ID from metadata (e.g., M-HP200, M-AC90)"
    )
    model = models.CharField(
        max_length=50,
        help_text="Machine Model Name (e.g., HP-200, AC-90)"
    )
    machine_name = models.CharField(
        max_length=200,
        help_text="Descriptive Machine Name (e.g., Hydraulic forming press)"
    )
    description = models.TextField(
        blank=True,
        help_text="Operational description or context"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['machine_id']
        verbose_name = 'Machine'
        verbose_name_plural = 'Machines'

    def __str__(self):
        return f"{self.model} ({self.machine_id}) - {self.machine_name}"
