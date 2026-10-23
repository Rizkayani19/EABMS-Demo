
from django.db.models import Sum
from django.contrib import messages
from django.shortcuts import redirect

@login_required
def reconcile_opening_balance(request):
    account = getattr(request, 'account', None)
    fy = getattr(request, 'fy', None)
    
    if not account or not fy:
        messages.error(request, 'No active account or financial year selected.')
        return redirect('core:home')
        
    # Get previous FY
    previous_fy = FinancialYear.objects.filter(end_date__lt=fy.start_date).order_by('-end_date').first()
    
    current_ob = OpeningBalance.objects.filter(account=account, financial_year=fy).first()
    
    calculated_balance = Decimal('0.00')
    has_variance = False
    variance_amount = Decimal('0.00')
    
    if previous_fy:
        prev_ob = OpeningBalance.objects.filter(account=account, financial_year=previous_fy).first()
        prev_ob_amount = prev_ob.balance_amount if prev_ob else Decimal('0.00')
        
        inflows = Transaction.objects.filter(
            account=account, financial_year=previous_fy, direction='INFLOW', status='ACTIVE'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        
        outflows = Transaction.objects.filter(
            account=account, financial_year=previous_fy, direction='OUTFLOW', status='ACTIVE'
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
        
        calculated_balance = prev_ob_amount + inflows - outflows
        
        if current_ob:
            variance_amount = current_ob.balance_amount - calculated_balance
            has_variance = variance_amount != Decimal('0.00')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'adopt_calculated' and previous_fy:
            if current_ob:
                current_ob.balance_amount = calculated_balance
                current_ob.remarks = f'Auto-reconciled from {previous_fy.name} closing balance.'
                current_ob.save()
            else:
                OpeningBalance.objects.create(
                    account=account, financial_year=fy, balance_amount=calculated_balance,
                    remarks=f'Auto-reconciled from {previous_fy.name} closing balance.'
                )
            messages.success(request, f'Successfully synchronized {fy.name} opening balance with previous closing balance.')
            return redirect('core:reconcile_opening_balance')
            
        elif action == 'edit_manual':
            new_amount = request.POST.get('new_amount')
            try:
                new_amount = Decimal(new_amount)
                if current_ob:
                    current_ob.balance_amount = new_amount
                    current_ob.remarks = 'Manually overridden.'
                    current_ob.save()
                else:
                    OpeningBalance.objects.create(account=account, financial_year=fy, balance_amount=new_amount, remarks='Manually overridden.')
                messages.success(request, 'Manual opening balance saved.')
            except:
                messages.error(request, 'Invalid amount.')
            return redirect('core:reconcile_opening_balance')
            
    context = {
        'previous_fy': previous_fy,
        'calculated_balance': calculated_balance,
        'current_ob': current_ob,
        'has_variance': has_variance,
        'variance_amount': variance_amount,
    }
    return render(request, 'core/reconcile_opening_balance.html', context)

