// All the wording the UI uses for states, reasons and tools lives in this one file.

export const REASONS = {
  clinical_urgent: { label: 'CLINICAL', tone: 'red', meaning: 'the caller described something that needs a clinician now' },
  medical_advice: { label: 'MEDICAL ADVICE', tone: 'red', meaning: 'the caller asked for a medical judgement the front desk cannot give' },
  not_authorised: { label: 'NOT AUTHORISED', tone: 'amber', meaning: 'the caller tried to act on a record that is not theirs' },
  ambiguous_patient: { label: 'AMBIGUOUS PATIENT', tone: 'amber', meaning: 'more than one patient matched and the agent will not guess' },
  out_of_scope: { label: 'OUT OF SCOPE', tone: 'grey', meaning: 'a real request the agent has no tool for' },
}

export const STATES = {
  booked: { tone: 'green', title: 'Booked', meaning: 'A new appointment was created.' },
  rescheduled: { tone: 'green', title: 'Rescheduled', meaning: 'An existing appointment was moved.' },
  cancelled: { tone: 'green', title: 'Cancelled', meaning: 'An existing appointment was cancelled.' },
  escalated: { tone: 'red', title: 'Handed to a human', meaning: 'Nothing was booked or changed.' },
  refused: { tone: 'grey', title: 'Refused', meaning: 'The agent declined the request. No tool changed anything and no human is needed.' },
  abandoned: { tone: 'grey', title: 'No action taken', meaning: 'The caller did not give enough to act on. Nothing was changed and no human is needed.' },
}

// Plain-English name for each tool, shown above the raw call.
export const TOOL_TITLES = {
  search_slots: 'Checked free slots',
  lookup_patient: 'Looked up the patient',
  book_appointment: 'Booked the appointment',
  reschedule_appointment: 'Moved the appointment',
  cancel_appointment: 'Cancelled the appointment',
  escalate_to_human: 'Handed the call to a human',
}
