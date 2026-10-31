"use client";
import {type AppDef,type AppScreen} from "@/lib/apps/registry";
import {PublishedWebsiteOffers} from "@/components/PublishedWebsiteOffers";
/** Public dealership promotions only. Private garage screens retain verification. */
export function MyGarageOffers({app,screen}:{app:AppDef;screen:AppScreen}){return <PublishedWebsiteOffers garage/>;}
