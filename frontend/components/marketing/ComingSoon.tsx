import Image from "next/image";
import showroom from "@/public/brand/nxtdeal-showroom.webp";
import { BrandLogo } from "@/components/BrandLogo";
import styles from "./ComingSoon.module.css";

export function ComingSoon() {
  return (
    <div className={styles.page}>
      <Image src={showroom} alt="" fill priority sizes="100vw" className={styles.scene} />
      <div className={styles.shade} />
      <div className={styles.content}>
        <header className={styles.header}>
          <BrandLogo />
          <span className={styles.status}><span /> Coming soon</span>
        </header>
        <main className={styles.main}>
          <section className={styles.intro} aria-labelledby="coming-soon-title">
            <p className={styles.eyebrow}>Dealerships today. A brighter tomorrow.</p>
            <h1 id="coming-soon-title">Your next chapter.<br /><span>In motion.</span></h1>
            <p className={styles.description}>One connected home for your dealership.<br />Your people, your data, your next move.</p>
            <div className={styles.pillars} aria-label="Our focus"><span>People</span><span>Process</span><span>Profit</span><span>Tomorrow</span></div>
          </section>
          <section className={styles.panel} aria-labelledby="next-heading">
            <div className={styles.orbit} aria-hidden="true"><span /><i /></div>
            <p className={styles.eyebrow}>Built for what comes next</p>
            <h2 id="next-heading">A new perspective.<br />A connected future.</h2>
            <p>We’re bringing the dealership together — with the clarity to see your business and the freedom to choose what comes next.</p>
            <a className={styles.contact} href="mailto:sambohon325@gmail.com?subject=NXTDeal%20launch%20interest">Let’s stay connected <span aria-hidden="true">↗</span></a>
            <span className={styles.note}>Get in touch about what’s ahead.</span>
          </section>
        </main>
        <footer className={styles.footer}><span>© {new Date().getFullYear()} Chronos. All rights reserved.</span><span>NXTDeal <span className={styles.divider}>/</span> Powered by Chrono</span></footer>
      </div>
    </div>
  );
}
