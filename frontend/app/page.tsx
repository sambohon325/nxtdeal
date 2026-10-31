import { BrandLogo } from "@/components/BrandLogo";
import styles from "./handoff.module.css";

const repository = "https://github.com/sambohon325/nxtdeal";

export default function Home() {
  return (
    <main className={styles.page}>
      <div className={styles.glow} aria-hidden="true" />
      <div className={styles.shell}>
        <header className={styles.header}>
          <BrandLogo />
          <span className={styles.status}><span aria-hidden="true" /> Community handoff</span>
        </header>

        <section className={styles.hero} aria-labelledby="handoff-heading">
          <p className={styles.eyebrow}>An open-source project</p>
          <h1 id="handoff-heading">The next chapter<br /><span>belongs to the community.</span></h1>
          <p className={styles.summary}>
            We’ve concluded our active development of NXTDeal to focus on other projects.
            The source is now public, and we’re excited to see what the community builds with it.
          </p>
          <div className={styles.actions}>
            <a className={styles.primary} href={repository}>
              Explore NXTDeal on GitHub <span aria-hidden="true">↗</span>
            </a>
            <a className={styles.secondary} href={`${repository}/blob/main/COMMUNITY-HANDOFF.md`}>
              Read the project handoff
            </a>
          </div>
        </section>

        <section className={styles.details} aria-label="Project information">
          <article>
            <span className={styles.number}>01</span>
            <h2>Open source</h2>
            <p>Browse the code and project notes in the public repository.</p>
          </article>
          <article>
            <span className={styles.number}>02</span>
            <h2>Community led</h2>
            <p>Development and support are now in the hands of community maintainers.</p>
          </article>
          <article>
            <span className={styles.number}>03</span>
            <h2>Early stage</h2>
            <p>The project is unfinished and has not been validated as production-ready.</p>
          </article>
        </section>

        <footer className={styles.footer}>
          <span>NXTDeal · Community handoff</span>
          <a href={`${repository}/blob/main/CONTRIBUTING.md`}>Contributing on GitHub <span aria-hidden="true">↗</span></a>
        </footer>
      </div>
    </main>
  );
}
