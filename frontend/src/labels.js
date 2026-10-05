// How each escalation reason is shown in the UI.
export const REASONS = {
  clinical_urgent: { label: 'CLINICAL', tone: 'red' },
  medical_advice: { label: 'MEDICAL ADVICE', tone: 'red' },
  not_authorised: { label: 'NOT AUTHORISED', tone: 'amber' },
  ambiguous_patient: { label: 'AMBIGUOUS PATIENT', tone: 'amber' },
  out_of_scope: { label: 'OUT OF SCOPE', tone: 'grey' },
}

export const STATE_TONES = {
  booked: 'green',
  rescheduled: 'green',
  cancelled: 'green',
  escalated: 'red',
  refused: 'grey',
  abandoned: 'grey',
}
