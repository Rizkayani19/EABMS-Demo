from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .budget_analysis_services import analyse_budget, variance_flags
from .budget_inflow_models import BudgetInflowLine
from .future_budget_calculation import calculate_future_budget_components
from .future_budget_inflow_proposal import get_user_proposed_inflow
from .future_budget_services import analyze_account_head, analyze_major_head, build_future_budget_lines
from .future_budget_workflow import FutureBudgetWorkflowService
from .models import AccountHead, BudgetLine, FinancialYear, FutureBudget, FutureBudgetLine, Transaction, MajorHead


class FutureBudgetPlanningView(LoginRequiredMixin, View):
    template_name = "finance/future_budget_planning.html"

    def get(self, request):
        account = request.account
        source_code = request.GET.get("source_fy") or (request.fy.code if request.fy else "")
        source_fy = FinancialYear.objects.filter(code=source_code).first() if source_code else None
        
        target_code = request.GET.get("target_fy", "").strip()
        if not target_code and source_fy:
            next_fy = FinancialYear.objects.filter(start_date__gt=source_fy.start_date).order_by('start_date').first()
            target_code = next_fy.code if next_fy else ""

        routine_pct = Decimal(request.GET.get("routine_adjustment", "0") or "0")
        inflow_pct = Decimal(request.GET.get("inflow_adjustment", "0") or "0")
        allocation_basis = request.GET.get("allocation_basis") or (account.budget_allocation_basis if account else "ACCOUNT_HEAD")

        target_fy = FinancialYear.objects.filter(code=target_code).first() if target_code else None
        context = {
            "account": account,
            "source_fy": source_fy,
            "target_fy": target_fy,
            "routine_adjustment": routine_pct,
            "inflow_adjustment": inflow_pct,
            "allocation_basis": allocation_basis,
            "analysis": None,
            "rows": [],
            "inflow_rows": [],
            "inflow_only_rows": [],
            "approved_future": None,
            "total_inflow_actual": Decimal("0.00"),
            "total_planned_inflows": Decimal("0.00"),
            "total_suggested_inflows": Decimal("0.00"),
            "net_budget_prev": Decimal("0.00"),
            "net_actual_prev": Decimal("0.00"),
            "net_suggested_future": Decimal("0.00"),
            "net_shift": Decimal("0.00"),
        }

        if not account or not source_fy or not target_fy:
            return render(request, self.template_name, context)

        approved_future = FutureBudget.objects.filter(
            account=account, source_fy=source_fy, target_fy=target_fy
        ).first()

        if allocation_basis == "SUB_FUND":
            analysis = analyse_budget(account, source_fy, allocation_basis="SUB_FUND")
            fb_lines_map = {l.major_head_id: l for l in approved_future.lines.all() if l.major_head_id} if approved_future else {}

            inflow_qs = Transaction.objects.filter(
                account=account,
                financial_year=source_fy,
                direction=Transaction.Direction.INFLOW,
                status=Transaction.Status.ACTIVE,
            )
            inflow_by_sf = {
                r["major_head_id"]: (r["total"] or Decimal("0.00"))
                for r in inflow_qs.exclude(major_head__isnull=True).values("major_head_id").annotate(total=Sum("amount"))
            }
            total_inflow_actual = sum(
                (r["total"] or Decimal("0.00") for r in inflow_qs.values("account_id").annotate(total=Sum("amount"))),
                Decimal("0.00")
            )

            sub_funds = MajorHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name')
            inflow_rows = []
            for sf in sub_funds:
                prev_budget = (
                    BudgetInflowLine.objects.filter(
                        budget__account=account,
                        budget__financial_year=source_fy,
                        major_head=sf,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                prev_actual = inflow_by_sf.get(sf.id, Decimal("0.00"))
                variance_amt = prev_actual - prev_budget
                variance_pct = (
                    ((variance_amt / prev_budget) * Decimal("100")).quantize(Decimal("0.01"))
                    if prev_budget > 0 else Decimal("0.00")
                )
                baseline = prev_actual if prev_actual > 0 else prev_budget
                suggested = (baseline + (baseline * inflow_pct / Decimal("100"))).quantize(Decimal("0.01"))

                existing_line = fb_lines_map.get(sf.id)
                existing_proposed_inflow = get_user_proposed_inflow(existing_line) if existing_line else None
                proposed_inflow = existing_proposed_inflow if existing_proposed_inflow is not None else suggested

                inflow_rows.append({
                    "head_id": sf.id,
                    "head": sf.name,
                    "code": sf.code or f"SF-{sf.id}",
                    "is_inflow_only": False,
                    "display_order": sf.display_order,
                    "previous_budget": prev_budget,
                    "previous_actual": prev_actual,
                    "variance_amount": variance_amt,
                    "variance_pct": variance_pct,
                    "suggested_future": suggested,
                    "proposed_inflow": proposed_inflow,
                })

            total_planned_inflows = sum((r["previous_budget"] for r in inflow_rows), Decimal("0.00"))
            total_suggested_inflows = sum((r["suggested_future"] for r in inflow_rows), Decimal("0.00"))

            rows = []
            for result_row in analysis["rows"]:
                sf_id = result_row["major_head_id"]
                sf = MajorHead.objects.filter(pk=sf_id).first()
                if not sf:
                    continue
                sf_analysis = analyze_major_head(account, source_fy, sf)
                previous_budget = (
                    BudgetLine.objects.filter(
                        budget__account=account,
                        budget__financial_year=source_fy,
                        major_head=sf,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                baseline = Decimal("0.00") if sf_analysis["is_onetime"] else sf_analysis["planning_actual"]
                calc = calculate_future_budget_components(
                    previous_actual=baseline,
                    routine_adj_pct=routine_pct,
                    continuing_amount=Decimal("0.00"),
                    known_change_amount=Decimal("0.00"),
                    personnel_amount=Decimal("0.00"),
                    onetime_amount=Decimal("0.00"),
                    additional_management_amount=Decimal("0.00"),
                )

                existing_line = fb_lines_map.get(sf.id)
                existing_user_proposed = existing_line.user_proposed if existing_line else None
                proposed_outflow = existing_user_proposed if existing_user_proposed is not None else calc.system_suggested

                rows.append({
                    "head_id": sf.id,
                    "head": sf.name,
                    "code": sf.code or f"SF-{sf.id}",
                    "previous_budget": previous_budget,
                    "historical_actual": sf_analysis["previous_actual"],
                    "planning_actual": sf_analysis["planning_actual"],
                    "pass_through": sf_analysis["pass_through_amount"],
                    "inflow_actual": inflow_by_sf.get(sf.id, Decimal("0.00")),
                    "is_routine": sf_analysis["is_routine"],
                    "is_onetime": sf_analysis["is_onetime"],
                    "system_suggested": calc.system_suggested,
                    "proposed_amount": proposed_outflow,
                    "nature_breakdown": sf_analysis.get("nature_breakdown", {}),
                })
            inflow_only_rows = []
        else:
            analysis = analyse_budget(account, source_fy, allocation_basis="ACCOUNT_HEAD")
            fb_lines_map = {l.account_head_id: l for l in approved_future.lines.all()} if approved_future else {}

            # ── Inflow actuals by account head ────────────────────────────────────
            inflow_qs = Transaction.objects.filter(
                account=account,
                financial_year=source_fy,
                direction=Transaction.Direction.INFLOW,
                status=Transaction.Status.ACTIVE,
            )
            inflow_by_head = {
                r["account_head_id"]: (r["total"] or Decimal("0.00"))
                for r in inflow_qs.values("account_head_id").annotate(total=Sum("amount"))
            }
            total_inflow_actual = sum(inflow_by_head.values(), Decimal("0.00"))

            # ── Comprehensive Inflow Planning Rows ──────────────────────────────
            inflow_heads_qs = AccountHead.objects.filter(
                account=account, is_active=True
            ).filter(
                Q(head_type__in=[AccountHead.HeadType.INFLOW, AccountHead.HeadType.BOTH]) |
                Q(id__in=inflow_by_head.keys())
            ).distinct().order_by('display_order', 'name')

            inflow_rows = []
            for h in inflow_heads_qs:
                prev_budget = (
                    BudgetInflowLine.objects.filter(
                        budget__account=account,
                        budget__financial_year=source_fy,
                        account_head=h,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                prev_actual = inflow_by_head.get(h.id, Decimal("0.00"))
                variance_amt = prev_actual - prev_budget
                variance_pct = (
                    ((variance_amt / prev_budget) * Decimal("100")).quantize(Decimal("0.01"))
                    if prev_budget > 0 else Decimal("0.00")
                )
                baseline = prev_actual if prev_actual > 0 else prev_budget
                suggested = (baseline + (baseline * inflow_pct / Decimal("100"))).quantize(Decimal("0.01"))
                
                existing_line = fb_lines_map.get(h.id)
                existing_proposed_inflow = get_user_proposed_inflow(existing_line) if existing_line else None
                proposed_inflow = existing_proposed_inflow if existing_proposed_inflow is not None else suggested

                inflow_rows.append({
                    "head_id": h.id,
                    "head": h.name,
                    "code": h.code,
                    "is_inflow_only": h.head_type == AccountHead.HeadType.INFLOW,
                    "display_order": h.display_order,
                    "previous_budget": prev_budget,
                    "previous_actual": prev_actual,
                    "variance_amount": variance_amt,
                    "variance_pct": variance_pct,
                    "suggested_future": suggested,
                    "proposed_inflow": proposed_inflow,
                })

            inflow_rows.sort(key=lambda r: (
                0 if r["is_inflow_only"] else 1,
                r["display_order"],
                r["head"],
            ))

            total_planned_inflows = sum((r["previous_budget"] for r in inflow_rows), Decimal("0.00"))
            total_suggested_inflows = sum((r["suggested_future"] for r in inflow_rows), Decimal("0.00"))

            # Inflow-only heads (present in inflows but NOT in outflow analysis)
            outflow_head_ids = {r["account_head_id"] for r in analysis["rows"]}
            inflow_only_head_ids = set(inflow_by_head.keys()) - outflow_head_ids
            inflow_only_heads = {
                h.id: h for h in AccountHead.objects.filter(id__in=inflow_only_head_ids)
            }

            heads = {
                h.id: h
                for h in AccountHead.objects.filter(
                    id__in={r["account_head_id"] for r in analysis["rows"]}
                )
            }

            # ── Outflow planning rows ─────────────────────────────────────────────
            rows = []
            for result_row in analysis["rows"]:
                head = heads[result_row["account_head_id"]]
                head_analysis = analyze_account_head(account, source_fy, head)
                previous_budget = (
                    BudgetLine.objects.filter(
                        budget__account=account,
                        budget__financial_year=source_fy,
                        account_head=head,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )
                baseline = Decimal("0.00") if head_analysis["is_onetime"] else head_analysis["planning_actual"]
                effective_pct = Decimal("0.00") if "salar" in head.name.lower() else routine_pct
                calc = calculate_future_budget_components(
                    previous_actual=baseline,
                    routine_adj_pct=effective_pct,
                    continuing_amount=Decimal("0.00"),
                    known_change_amount=Decimal("0.00"),
                    personnel_amount=Decimal("0.00"),
                    onetime_amount=Decimal("0.00"),
                    additional_management_amount=Decimal("0.00"),
                )

                existing_line = fb_lines_map.get(head.id)
                existing_user_proposed = existing_line.user_proposed if existing_line else None
                proposed_outflow = existing_user_proposed if existing_user_proposed is not None else calc.system_suggested

                rows.append({
                    "head_id": head.id,
                    "head": head.name,
                    "code": head.code,
                    "previous_budget": previous_budget,
                    "historical_actual": head_analysis["previous_actual"],
                    "planning_actual": head_analysis["planning_actual"],
                    "pass_through": head_analysis["pass_through_amount"],
                    "inflow_actual": inflow_by_head.get(head.id, Decimal("0.00")),
                    "is_routine": head_analysis["is_routine"],
                    "is_onetime": head_analysis["is_onetime"],
                    "system_suggested": calc.system_suggested,
                    "proposed_amount": proposed_outflow,
                    "nature_breakdown": head_analysis.get("nature_breakdown", {}),
                })

            # ── Inflow-only rows (legacy compatibility) ───────────────────────────
            inflow_only_rows = sorted([
                {"head": head.name, "inflow_actual": inflow_by_head.get(hid, Decimal("0.00"))}
                for hid, head in inflow_only_heads.items()
            ], key=lambda r: -r["inflow_actual"])

        # ── Net Fiscal Position Matrix ────────────────────────────────────────
        total_approved_outflow_budget = analysis["total_budget"]
        total_outflow_actual = analysis["total_actual"]
        planning_total = sum((r["planning_actual"] for r in rows), Decimal("0.00"))
        suggested_total = sum((r["system_suggested"] for r in rows), Decimal("0.00"))

        net_budget_prev = total_planned_inflows - total_approved_outflow_budget
        net_actual_prev = total_inflow_actual - total_outflow_actual
        net_suggested_future = total_suggested_inflows - suggested_total
        net_shift = net_suggested_future - net_actual_prev

        context.update({
            "analysis": analysis,
            "rows": rows,
            "inflow_rows": inflow_rows,
            "inflow_only_rows": inflow_only_rows,
            "approved_future": approved_future,
            "material_flags": variance_flags(analysis),
            "planning_total": planning_total,
            "suggested_total": suggested_total,
            "total_inflow_actual": total_inflow_actual,
            "total_planned_inflows": total_planned_inflows,
            "total_suggested_inflows": total_suggested_inflows,
            "total_approved_outflow_budget": total_approved_outflow_budget,
            "total_outflow_actual": total_outflow_actual,
            "net_budget_prev": net_budget_prev,
            "net_actual_prev": net_actual_prev,
            "net_suggested_future": net_suggested_future,
            "net_shift": net_shift,
        })
        return render(request, self.template_name, context)

    def post(self, request):
        account = request.account
        source_code = request.POST.get("source_fy", "").strip()
        target_code = request.POST.get("target_fy", "").strip()
        routine_pct = Decimal(request.POST.get("routine_adjustment", "0") or "0")
        inflow_pct = Decimal(request.POST.get("inflow_adjustment", "0") or "0")
        allocation_basis = request.POST.get("allocation_basis") or (account.budget_allocation_basis if account else "ACCOUNT_HEAD")
        action = request.POST.get("action", "save_draft").strip()

        source_fy = FinancialYear.objects.filter(code=source_code).first()
        target_fy = FinancialYear.objects.filter(code=target_code).first()

        if not account or not source_fy or not target_fy:
            messages.error(request, "Valid Source and Target Financial Years are required.")
            return redirect("core:future_budget_planning")

        fb, created = FutureBudget.objects.get_or_create(
            account=account,
            source_fy=source_fy,
            target_fy=target_fy,
            defaults={
                "routine_adjustment_pct": routine_pct,
                "budget_allocation_basis": allocation_basis,
                "created_by": request.user,
                "status": FutureBudget.Status.DRAFT,
                "reference": f"Planning Budget {source_fy.code} -> {target_fy.code}",
                "remarks": f"Generated from Budget Planning ({allocation_basis}, Routine Adj: {routine_pct}%, Inflow Adj: {inflow_pct}%)",
            }
        )
        if not created:
            fb.budget_allocation_basis = allocation_basis
            fb.routine_adjustment_pct = routine_pct
            fb.updated_by = request.user
            fb.save(update_fields=["budget_allocation_basis", "routine_adjustment_pct", "updated_by", "updated_at"])

        if allocation_basis == "SUB_FUND":
            if not fb.lines.exists() and fb.status != FutureBudget.Status.APPROVED:
                build_future_budget_lines(fb)

            # Update outflow proposals
            outflow_head_ids = request.POST.getlist("outflow_head_ids")
            for sf_id in outflow_head_ids:
                raw = request.POST.get(f"outflow_proposed_{sf_id}", "").strip()
                if raw:
                    try:
                        amt = Decimal(raw)
                        sf = MajorHead.objects.get(pk=sf_id)
                        line = fb.lines.filter(major_head=sf, account_head__isnull=True).first()
                        if not line:
                            line = FutureBudgetLine.objects.create(
                                future_budget=fb,
                                major_head=sf,
                                account_head=None,
                                previous_budget=Decimal("0.00"),
                                previous_actual=Decimal("0.00"),
                                system_suggested=amt,
                            )
                        FutureBudgetWorkflowService.propose(
                            line, amt, request.user,
                            justification=request.POST.get(f"outflow_justification_{sf_id}", "").strip() or "Entered via Budget Planning (Sub-Fund)",
                        )
                    except Exception:
                        pass

            # Update inflow proposals
            inflow_head_ids = request.POST.getlist("inflow_head_ids")
            for sf_id in inflow_head_ids:
                raw = request.POST.get(f"inflow_proposed_{sf_id}", "").strip()
                if raw:
                    try:
                        amt = Decimal(raw)
                        sf = MajorHead.objects.get(pk=sf_id)
                        line = fb.lines.filter(major_head=sf, account_head__isnull=True).first()
                        if not line:
                            line = FutureBudgetLine.objects.create(
                                future_budget=fb,
                                major_head=sf,
                                account_head=None,
                                previous_budget=Decimal("0.00"),
                                previous_actual=Decimal("0.00"),
                                system_suggested=Decimal("0.00"),
                            )
                        FutureBudgetWorkflowService.propose_inflow(
                            line, amt, request.user,
                            justification=request.POST.get(f"inflow_justification_{sf_id}", "").strip() or "Entered via Budget Planning (Sub-Fund)",
                        )
                    except Exception:
                        pass
        else:
            active_master_head_ids = set(
                AccountHead.objects.filter(account=fb.account, is_active=True).values_list('id', flat=True)
            )
            existing_line_head_ids = set(fb.lines.values_list('account_head_id', flat=True))
            if (not fb.lines.exists() or (active_master_head_ids - existing_line_head_ids)) and fb.status != FutureBudget.Status.APPROVED:
                build_future_budget_lines(fb)

            # Update outflow proposals
            outflow_head_ids = request.POST.getlist("outflow_head_ids")
            for hid in outflow_head_ids:
                raw = request.POST.get(f"outflow_proposed_{hid}", "").strip()
                if raw:
                    try:
                        amt = Decimal(raw)
                        ah = AccountHead.objects.get(pk=hid)
                        line = fb.lines.filter(account_head=ah).first()
                        if not line:
                            line = FutureBudgetLine.objects.create(
                                future_budget=fb,
                                account_head=ah,
                                major_head=ah.major_head,
                                sub_head=ah.sub_head,
                                previous_budget=Decimal("0.00"),
                                previous_actual=Decimal("0.00"),
                                system_suggested=amt,
                            )
                        FutureBudgetWorkflowService.propose(
                            line, amt, request.user,
                            justification=request.POST.get(f"outflow_justification_{hid}", "").strip() or "Entered via Budget Planning",
                        )
                    except Exception:
                        pass

            # Update inflow proposals
            inflow_head_ids = request.POST.getlist("inflow_head_ids")
            for hid in inflow_head_ids:
                raw = request.POST.get(f"inflow_proposed_{hid}", "").strip()
                if raw:
                    try:
                        amt = Decimal(raw)
                        ah = AccountHead.objects.get(pk=hid)
                        line = fb.lines.filter(account_head=ah).first()
                        if not line:
                            line = FutureBudgetLine.objects.create(
                                future_budget=fb,
                                account_head=ah,
                                major_head=ah.major_head,
                                sub_head=ah.sub_head,
                                previous_budget=Decimal("0.00"),
                                previous_actual=Decimal("0.00"),
                                system_suggested=Decimal("0.00"),
                            )
                        FutureBudgetWorkflowService.propose_inflow(
                            line, amt, request.user,
                            justification=request.POST.get(f"inflow_justification_{hid}", "").strip() or "Entered via Budget Planning",
                        )
                    except Exception:
                        pass

        if action == "submit_proposed":
            fb.status = FutureBudget.Status.PROPOSED
            fb.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Future Budget #{fb.pk} ({target_fy.code}) submitted for management review with custom inflow and outflow proposals.")
        else:
            fb.status = FutureBudget.Status.DRAFT
            fb.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Draft Future Budget #{fb.pk} ({target_fy.code}) saved with custom inflow and outflow proposals.")

        return redirect("core:future_budget_review", pk=fb.pk)
