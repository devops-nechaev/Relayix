# Personal delivery failure alerts — proposal

Status: deferred by user request on 2026-11-07 to the release after 0.8.1. Version 0.8.1 includes interface items 1–6; personal delivery alert subscriptions (item 7) remain planned.

Visual mockup: [interface-options.html](interface-options.html), section C.
Personal subscriptions and recovery notifications are proposed for a later implementation. Working shared rules are already available to administrators in Failure alerts.

Add a Delivery alerts section to My profile, separate from Interface notifications, which controls the duration of interface banners.

Users choose existing channels, routes to watch and a trigger condition. Default: final failure after five unsuccessful attempts. Optional modes: the first retry error or a threshold within a time window. Default repeat interval: 15 minutes. Support multiple recipients and recommend an independent channel. Email uses a configured SMTP channel.

An alert includes the route, channel, timestamp, attempt count, a safe error summary and a link to event details. Temporary errors appear as Retrying; final failures appear as Failed. Details provides attempt history and manual retry. Show fallback results separately, since a failed primary destination can still have a successful fallback delivery.

Reuse alert_policies, alert_incidents and alert_deliveries for thresholds, cooldown, a separate queue with retries and protection against recursive alerts. Add owner_user_id referencing users and distinguish shared rules from personal subscriptions. Existing rules stay shared. Enforce ownership on the server for reads, changes, deletion, testing and history. Preserve administrator access to shared rules. Disabled users must not send subscription alerts.

Current min_attempts=5 is an attempt threshold rather than a strict final-failure condition: manual retries preserve the total attempt count. Add an explicit status='failed' condition for final failures. For early warnings, account for queued deliveries with errors and the active retry cycle.

Limit noise with one incident per delivery and subscription, grouped errors by route/channel, and cooldown. Track retry cycles so a new final failure after a manual retry is not suppressed by an earlier alert_incidents record.

Optional recovery notifications require explicit incident state. Send one recovery notice only after a previous warning and a successful delivery of the same message. Distinguish recovery of the primary delivery from successful fallback. Track resolved_at and recovery notification independently of the failure cooldown.

Before release, verify isolation between users, disabled owners, final-failure and manual-retry conditions, deduplication and cooldown, independent recipients, alert failure without recursion, a single recovery notice, removed or disabled channels and routes, and the absence of credentials or sensitive content in error summaries.
