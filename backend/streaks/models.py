from django.conf import settings
from django.db import models


class WeeklyComparison(models.Model):
    """The outcome of an account's most recent completed cart comparison in one
    calendar week (Vienna time, weeks start on Monday).

    One row per account and week: comparing again the same week replaces the
    row instead of adding to it, so re-running a comparison can't inflate the
    savings, and the streak simply counts the weeks that have a row.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_comparisons"
    )
    week_start = models.DateField(help_text="The Monday of the week this comparison counts for.")
    savings_vs_most_expensive = models.DecimalField(max_digits=10, decimal_places=2)
    savings_vs_regular = models.DecimalField(max_digits=10, decimal_places=2)
    # Per-product breakdown: [{name, brand, advertiser, savings_vs_most_expensive,
    # savings_vs_regular, on_sale}] — what the "which stores/products contributed"
    # part of the summary is derived from.
    items = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "week_start"], name="one_weekly_comparison_per_user_and_week"
            )
        ]

    def __str__(self):
        return f"WeeklyComparison({self.user_id}, {self.week_start})"
