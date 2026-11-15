# mdce
final project for 1st sem (client: mdce transpo)
- fully functioning website where they can put:
    - documents
    - drivers info
    - jeepneys info
    - issues from jeeps
  - only admins can use it
  - i plan to put offline mode if possible
  - use ocr as suggested for files
[files and images used is just for samples only]

## Project Overview

MDCE FleetHub is an administrative information system for the staff of MDCE Transport Services OPC. It brings fleet records, driver information, vehicle documents, and issue reports together in one web application.

The system is intended to make these records easier to organize, find, review, and maintain.

## How the System Works

An administrator logs in to access the system. From the dashboard, they can open the system’s main modules. Records and uploaded files are stored in the system’s database and file storage so staff can return to them later.

The system connects related information. For example, a jeep profile can show its assigned driver and documents linked to that jeep. Issue reports can also be connected to a jeep and, when applicable, its driver.

## Main Modules

### FleetHub

FleetHub manages jeep and driver records. Administrators can add, view, and update their information. Dedicated profiles bring each jeep’s or driver’s details and related documents together.

### DockTrack

DockTrack stores documents associated with a jeep or driver, such as ORs, CRs, decisions, and other document types. Administrators can select a file to preview it before saving it.

DockTrack also includes OCR for reading printed text from supported PDFs and images. Recognized text appears beside the preview for staff to review. OCR does not fill the form automatically, and its results may contain errors. PDF OCR is limited to 10 pages per file.

### IssueTrack

IssueTrack records jeep-related issues and repair information, including status, dates, costs, and other available details. Administrators can view an issue separately from editing it and can update its status as work progresses.

### Activity Log

The Activity Log provides a record of actions performed in the system, helping administrators review recent system activity.

### Administrator Accounts

The system provides administrator login, profile management, registration, and password reset. Password reset links are sent by email through the connected email service.

## Validation and Record Keeping

The system validates form data before saving it. This helps prevent missing or invalid information from being stored. Flask processes the application’s requests and validation, while MySQL stores structured records and their relationships.

Uploaded documents and issue photos are stored as files. Their paths and related information are recorded in the database.

## Purpose and Benefits

MDCE FleetHub is designed to give staff one place to manage fleet information and related records. Its modules help administrators:

- Find jeep and driver information through profiles.
- Keep documents associated with the correct jeep or driver.
- Review repair issues and their status.
- Preview documents and use OCR as an aid when reading printed text.
- Review recent actions through the Activity Log.
