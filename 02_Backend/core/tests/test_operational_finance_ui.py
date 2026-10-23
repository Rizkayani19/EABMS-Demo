from django.test import SimpleTestCase

from core.forms import InflowForm, OutflowForm, ReimbursementForm


class OperationalFinanceUIContractTests(SimpleTestCase):
    def test_inflow_form_contract(self):
        form = InflowForm()
        for field in [
            'transaction_date', 'account_head', 'amount', 'inflow_type',
            'payee_or_source', 'reference', 'description',
            'transaction_units', 'transaction_sections', 'remarks',
        ]:
            self.assertIn(field, form.fields)

    def test_outflow_form_contract(self):
        form = OutflowForm()
        for field in [
            'transaction_date', 'account_head', 'sub_head', 'amount',
            'outflow_nature', 'payee_or_source', 'purpose', 'reference',
            'pass_through', 'transaction_units', 'transaction_sections',
            'remarks',
        ]:
            self.assertIn(field, form.fields)
        self.assertEqual(form.fields['account_head'].widget.attrs.get('hx-target'), '#id_sub_head')

    def test_reimbursement_form_contract(self):
        form = ReimbursementForm()
        for field in [
            'reimbursement_type', 'expected_amount', 'expected_date',
            'source', 'reference', 'status', 'remarks',
        ]:
            self.assertIn(field, form.fields)
