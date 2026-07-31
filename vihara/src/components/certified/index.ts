/**
 * The certified layer's one door (R-4 part C).
 *
 * A surface that takes a certified act imports `useCertifiedAct` and
 * `StepUpCeremony` from here and nothing else from this directory. The barrel
 * is not tidiness: `tests/certified.test.tsx` asserts that no module outside
 * this directory reaches past it, which is what makes "every certified control
 * routes through the hook" (C2) a checked statement rather than a convention.
 */
export {
  CERTIFIED_ACTS,
  CERTIFIED_TYPES,
  gateFor,
  type CertifiedActEntry,
  type CertifiedType,
  type CeremonyType,
  type Gate,
  type RunnableCertifiedType,
} from "./acts";

export {
  CERTIFIED_IMPLEMENTATIONS,
  CertifiedApproval,
  CertifiedAutonomyChange,
  CertifiedConnectorBinding,
  CertifiedConsent,
  CertifiedMasteringDeclaration,
  CertifiedPayment,
  CertifiedProviderOptIn,
  CertifiedSecondChannelWait,
  CertifiedStepUp,
  CertifiedStrategyResolution,
  type CertifiedProps,
} from "./certifiedSet";

export {
  StepUpCeremony,
  type CeremonyDeps,
  type CeremonyPrompt,
  type StepUpCeremonyProps,
} from "./StepUpCeremony";

export {
  useCertifiedAct,
  type CertifiedAct,
  type CertifiedActOptions,
  type CertifiedProblem,
  type CertifiedRequest,
  type EchoRenderer,
} from "./useCertifiedAct";

export {
  isNoPasskeyEnrolled,
  isStepUpLockout,
  readStepUpRefusal,
  stepUpLockoutReason,
  type CertifiedRefusal,
} from "./refusal";
