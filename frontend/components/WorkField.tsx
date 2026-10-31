"use client";
import { isValidElement, type ReactNode } from "react";
import "./WorkField.css";
/** Persistent labels keep a field understandable after a value has been entered. */
export function WorkField({label,children}:{label:ReactNode;children:ReactNode}) {
 const required=isValidElement<{required?:boolean}>(children)&&children.props.required;
 return <label className="work-field"><span className="work-field-label">{label}{required&&<span aria-hidden="true"> *</span>}</span>{children}</label>;
}
